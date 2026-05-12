from dotenv import load_dotenv
import os

load_dotenv()

print("SUPABASE URL:")
print(os.getenv("SUPABASE_URL"))

print("\nANON KEY EXISTS:")
print(bool(os.getenv("SUPABASE_ANON_KEY")))

print("\nSERVICE KEY EXISTS:")
print(bool(os.getenv("SUPABASE_SERVICE_KEY")))