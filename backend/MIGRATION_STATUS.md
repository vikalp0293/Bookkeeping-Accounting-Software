# Database Migration Status

## Migration Chain

1. **db0c4c45dea2** (Initial Migration)
   - Creates: `users`, `login_sessions`, `workspaces`, `files`, `extracted_data`
   - Creates ENUM: `filestatus`

2. **add_payee_review_queue** (Revises: db0c4c45dea2)
   - Creates: `categories`, `vendors`, `payees`, `payee_corrections`, `review_queue`, `local_directories`
   - Creates ENUMs: `reviewpriority`, `reviewstatus`, `reviewreason`

3. **add_qb_transaction_queue** (Revises: add_payee_review_queue)
   - Creates: `qb_transaction_queue`
   - Creates ENUM: `qb_transaction_status`

## Expected Tables

1. `users` - User accounts
2. `login_sessions` - User authentication sessions
3. `workspaces` - Workspace/organization containers
4. `files` - Uploaded files
5. `extracted_data` - Extracted data from files
6. `categories` - Transaction categories
7. `vendors` - Vendor information
8. `payees` - Payee information
9. `payee_corrections` - Payee correction history
10. `review_queue` - Items requiring review
11. `local_directories` - Local directory monitoring config
12. `qb_transaction_queue` - QuickBooks sync queue

## Expected ENUM Types

1. `filestatus` - ['UPLOADED', 'PROCESSING', 'COMPLETED', 'FAILED']
2. `reviewpriority` - ['HIGH', 'MEDIUM', 'LOW']
3. `reviewstatus` - ['PENDING', 'IN_REVIEW', 'APPROVED', 'REJECTED', 'COMPLETED', 'SKIPPED']
4. `reviewreason` - ['LOW_CONFIDENCE', 'MISSING_FIELDS', 'NON_ENGLISH', 'NO_PAYEE_MATCH', 'USER_FLAGGED', 'PAYEE_CORRECTION', 'OTHER']
5. `qb_transaction_status` - ['pending', 'queued', 'syncing', 'synced', 'failed']

## How to Check Migration Status

### On Server (via SSH or deployment script):
```bash
cd /path/to/backend
alembic current    # Shows current migration version
alembic heads       # Shows latest migration version
alembic history     # Shows all migrations
```

### Check if migrations are needed:
```bash
alembic current
alembic heads
# If current != heads, run: alembic upgrade head
```

### Run pending migrations:
```bash
alembic upgrade head
```

## Quick Check Commands

```sql
-- Check all tables exist
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;

-- Check all ENUMs exist
SELECT typname 
FROM pg_type 
WHERE typtype = 'e' 
ORDER BY typname;

-- Check Alembic version
SELECT version_num FROM alembic_version;
```

