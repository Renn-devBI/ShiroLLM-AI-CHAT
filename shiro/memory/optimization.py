"""
Memory Optimization Module
Untuk mencegah hallucination pada conversations panjang
"""

def get_smart_memory_context(memory, limit=10, include_important=True):
    """
    Get memory dengan strategi cerdas:
    1. Selalu ambil N pesan terakhir (recent)
    2. Jika ada, tambah pesan dengan emosi tinggi (important)
    3. Total tidak boleh melebihi limit
    
    Args:
        memory: AdvancedMemoryManager instance
        limit: Max messages to load (default: 10)
        include_important: Include high-emotion messages (default: True)
    
    Returns:
        List of messages sorted by timestamp
    """
    history = memory.short_term_history
    
    if not history:
        return []
    
    # 1. Always get recent messages (70% of budget)
    recent_count = max(5, int(limit * 0.7))
    recent = history[-recent_count:]
    
    # 2. If enough budget, add important messages (30% of budget)
    important = []
    if include_important and len(recent) < limit:
        remaining_budget = limit - len(recent)
        
        # Get messages with high emotional content
        important_msgs = [
            m for m in history 
            if m.get('emotion') in ['romantic', 'jealous', 'angry'] or
               any(word in m.get('content', '').lower() 
                   for word in ['sayang', 'cinta', 'kangen', 'rindu', 'marah'])
        ]
        
        # Add oldest important messages (before recent)
        for msg in important_msgs:
            if msg not in recent and len(important) < remaining_budget:
                important.append(msg)
    
    # 3. Combine and sort by timestamp (deduplicate without set(dicts))
    combined = []
    seen_keys = set()
    for msg in [*recent, *important]:
        key = msg.get('timestamp') or (msg.get('role', ''), msg.get('content', ''))
        if key not in seen_keys:
            seen_keys.add(key)
            combined.append(msg)
    
    combined.sort(key=lambda x: x.get('timestamp', ''))
    return combined


def compress_old_messages(memory, keep_count=15):
    """
    Compress old messages into facts to save tokens
    
    Args:
        memory: AdvancedMemoryManager instance
        keep_count: How many recent messages to keep (default: 15)
    """
    if len(memory.short_term_history) <= keep_count:
        return  # Nothing to compress
    
    old_messages = memory.short_term_history[:-keep_count]
    
    # Extract facts from old messages
    for msg in old_messages:
        if msg.get('role') == 'user':
            facts = memory._extract_rdf_facts(msg.get('content', ''), 'user')
            memory.knowledge_base['facts'].extend(facts)
    
    # Keep only recent messages
    memory.short_term_history = memory.short_term_history[-keep_count:]
    
    print(f"[Memory] Compressed {len(old_messages)} old messages into facts")
    print(f"[Memory] Now storing {len(memory.short_term_history)} recent messages")


def diagnose_memory_status(memory, context_window=8192):
    """
    Diagnose current memory usage and hallucination risk
    
    Returns:
        Dict dengan diagnostic info
    """
    import math
    
    total_messages = len(memory.short_term_history)
    total_facts = len(memory.knowledge_base.get('facts', []))
    
    # Estimate tokens
    tokens_per_message = 100  # Average
    tokens_per_fact = 30
    
    est_history_tokens = total_messages * tokens_per_message
    est_facts_tokens = total_facts * tokens_per_fact
    est_system_tokens = 250  # System prompt
    est_response_budget = 800
    
    total_used = est_history_tokens + est_facts_tokens + est_system_tokens + est_response_budget
    available = context_window - est_response_budget
    
    hallucination_risk = "LOW" if total_used < available * 0.7 else \
                         "MEDIUM" if total_used < available * 0.9 else "HIGH"
    
    return {
        "total_messages": total_messages,
        "total_facts": total_facts,
        "est_tokens_used": total_used,
        "context_window": context_window,
        "tokens_available": available,
        "hallucination_risk": hallucination_risk,
        "recommendation": (
            "Reduce context limit to 8" if hallucination_risk == "HIGH" else
            "Current config acceptable" if hallucination_risk == "LOW" else
            "Monitor for hallucinations"
        )
    }


def calculate_token_budget(context_window=8192, max_response=800, system_overhead=250):
    """
    Calculate available token budget for conversation history and memory facts.
    
    Args:
        context_window: Total context window size (default: 8192)
        max_response: Allocated tokens for model generation (default: 800)
        system_overhead: Approximate tokens for system prompt and instructions (default: 250)
        
    Returns:
        Available token budget
    """
    return max(500, context_window - max_response - system_overhead)


def estimate_tokens(text: str) -> int:
    """
    Estimate token count for Indonesian & English text.
    Conservative: ~3 characters per token to ensure safety against context overflow.
    """
    if not text:
        return 0
    return int(len(text) / 3.0) + 2


def calculate_messages_tokens(messages, model=None) -> int:
    """
    Calculate total tokens used by a list of chat completion messages.
    Uses model.tokenize if available, otherwise falls back to estimate_tokens.
    """
    total = 0
    for m in messages:
        c = m.get("content", "")
        if isinstance(c, str):
            if model is not None and hasattr(model, "tokenize"):
                try:
                    total += len(model.tokenize(c.encode("utf-8", errors="ignore"))) + 4
                    continue
                except Exception:
                    pass
            total += estimate_tokens(c) + 4
        elif isinstance(c, list):
            for part in c:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        txt = part.get("text", "")
                        if model is not None and hasattr(model, "tokenize"):
                            try:
                                total += len(model.tokenize(txt.encode("utf-8", errors="ignore"))) + 4
                                continue
                            except Exception:
                                pass
                        total += estimate_tokens(txt) + 4
                    elif part.get("type") == "image_url":
                        total += 576  # Standard vision patch tokens
    return total


def trim_text_to_token_budget(text: str, max_tokens: int, suffix: str = "\n\n... [Teks dipotong agar pas dalam batas memori AI] ...") -> str:
    """
    Trim long text to fit within a specific token budget cleanly.
    """
    if not text or max_tokens <= 0:
        return ""
    
    current_tokens = estimate_tokens(text)
    if current_tokens <= max_tokens:
        return text
    
    suffix_tokens = estimate_tokens(suffix)
    allowed_content_tokens = max(50, max_tokens - suffix_tokens)
    max_chars = int(allowed_content_tokens * 3.0)
    
    if len(text) <= max_chars:
        return text
    
    truncated = text[:max_chars]
    # Try to break cleanly at paragraph or newline boundary
    last_newline = truncated.rfind("\n")
    if last_newline > int(max_chars * 0.75):
        truncated = truncated[:last_newline]
    else:
        last_space = truncated.rfind(" ")
        if last_space > int(max_chars * 0.85):
            truncated = truncated[:last_space]
            
    return truncated + suffix


# Usage Examples:
"""
# In web.py, replace this:
recent_context = memory.get_memory_context(limit=15)

# With this:
from memory_optimization import get_smart_memory_context
recent_context = get_smart_memory_context(memory, limit=10)

# To compress old messages periodically:
from memory_optimization import compress_old_messages
if total_turns % 20 == 0:  # Every 20 messages
    compress_old_messages(memory, keep_count=15)

# To diagnose issues:
from memory_optimization import diagnose_memory_status
status = diagnose_memory_status(memory)
print(f"Hallucination risk: {status['hallucination_risk']}")
"""
