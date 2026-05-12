# Tarasi Neon Schema

Apply the schema:

```bash
psql "$DATABASE_URL" -f database/bookme_neon_schema.sql
```

Verify the tables:

```bash
psql "$DATABASE_URL" -c "\dt"
```
