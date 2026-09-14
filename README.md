# market-dashboard
A full-stack market intelligence dashboard for stocks and futures

1. Copy .env.example to .env and fill in your credentials

2. Create or update the database tables:

   ```powershell
   py -3.14 -B scripts/migrate.py
   ```
