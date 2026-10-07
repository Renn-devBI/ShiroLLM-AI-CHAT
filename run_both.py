import subprocess
import os
import sys

if __name__ == '__main__':
    print("\n" + "="*60)
    print("✨ SHIRO - Interface Choice ✨")
    print("="*60)
    print("\nPilih interface:")
    print("1. CLI only (app.py)")
    print("2. Web only (web.py)")
    print("3. CLI + Web (recommended)")
    print("-" * 60)
    
    choice = input("Pilih (1/2/3): ").strip()
    
    if choice == "1":
        print("\nMenjalankan CLI...\n")
        subprocess.run([sys.executable, 'app.py'])
    
    elif choice == "2":
        print("\nMenjalankan Web Server...\n")
        print("✓ Akses: http://localhost:5000")
        print("- Pastikan app.py pernah dijalankan sebelumnya\n")
        subprocess.run([sys.executable, 'web.py'])
    
    elif choice == "3":
        print("\nMenjalankan CLI + Web...")
        print("- Terminal ini: CLI input")
        print("- Browser: http://localhost:5000")
        print("- Ketik 'exit' atau 'keluar' di CLI untuk quit\n")
        
        # Jalankan app.py - ini akan block sampai 'exit' ditekan
        subprocess.run([sys.executable, 'app.py'])
        
        # Setelah app.py exit, shutdown web server
        print("\nShutdown...")
    
    else:
        print("Invalid choice")
    
    print("Done!")
    os._exit(0)
