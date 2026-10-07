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


def diagnose_memory_status(memory, context_window=4096):
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
