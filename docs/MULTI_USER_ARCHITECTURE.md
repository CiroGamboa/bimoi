# Multi-User Architecture

## Overview

Bimoi is a **multi-user system** where each Telegram user gets their own isolated contact graph. The system uses an identity layer to map Telegram users to stable internal user IDs, and all contact data is scoped per user.

## How Multi-User Works

### Identity Layer

Located in `src/bimoi/infrastructure/identity.py`, the identity layer provides:

1. **Channel-agnostic identity**: Maps `(channel, external_id)` → `user_id` (Account UUID)
   - `channel`: e.g., "telegram" (future: "whatsapp", "web")
   - `external_id`: e.g., Telegram user ID (integer as string)
   - `user_id`: Stable UUID that identifies the user across channels

2. **Account creation**: First time a Telegram user interacts, an Account node is created in Neo4j with a unique UUID

3. **User lookup**: Subsequent interactions resolve the Telegram ID to the same `user_id`

### Neo4j Graph Model

```
┌─────────────────┐
│  ChannelLink    │
│  channel: "telegram"
│  external_id: "123456789"
└────────┬────────┘
         │ :BELONGS_TO
         ▼
┌─────────────────┐
│    Account      │
│  id: <UUID>     │  (user_id)
│  name: "Alice"  │
└────────┬────────┘
         │
         │ represented by
         ▼
┌─────────────────┐        ┌─────────────────┐
│  Person (owner) │        │ Person (contact)│
│  id: <user_id>  │──KNOWS→│ id: <UUID>      │
│  registered: true│        │ registered: false│
└─────────────────┘        └─────────────────┘
                   ╲
                    ╲ context properties:
                     • context_id
                     • context_description
                     • context_created_at
                     • context_updated_at
```

**Key points:**
- Each user has a Person node with `registered: true` and `id = user_id`
- Each contact is a Person node with `registered: false`
- Context is stored on the KNOWS relationship (not a separate node)
- All queries filter by owner's `user_id`, ensuring data isolation

### Per-User Service Isolation

In `src/api/main.py`:

```python
# Per-user ContactService cache
_service_cache: dict[str, ContactService] = {}

def get_service(user_id: str, app: FastAPI) -> ContactService:
    driver = _get_cached_driver(app)
    if user_id not in _service_cache:
        repo = Neo4jContactRepository(driver, user_id=user_id)
        _service_cache[user_id] = ContactService(repo)
    return _service_cache[user_id]
```

- Each `user_id` gets its own `ContactService` instance
- Each `ContactService` has its own `Neo4jContactRepository` scoped to that user
- Pending contact state (card received, context not yet submitted) is isolated per user

### Webhook Flow

When a Telegram update arrives at `/webhook/telegram`:

1. **Extract Telegram user ID**: `update.effective_user.id`
2. **Resolve to user_id**:
   ```python
   user_id, is_new_user = get_or_create_user_id(
       driver,
       CHANNEL_TELEGRAM,
       str(update.effective_user.id),
       initial_name=initial_name,
   )
   ```
3. **Get user's service**: `service = get_service(user_id, app)`
4. **Process update**: All operations (add contact, list, search) use that user's service
5. **Send response**: Reply goes back to the Telegram chat

### REST API Multi-User Support

REST endpoints support multi-user via the `X-User-Id` header:

```bash
# List contacts for user "abc-123"
curl -H "X-User-Id: abc-123" http://localhost:8010/contacts

# Search contacts for user "xyz-789"
curl -H "X-User-Id: xyz-789" http://localhost:8010/contacts/search?q=friend
```

If no header is provided, defaults to `"default"` user ID.

## Authentication

- **Telegram bot**: Authentication is handled by Telegram itself. Only the user who owns a Telegram account can send updates from that account.
- **REST API**: Currently uses `X-User-Id` header without verification (suitable for trusted environments). Future iterations could add proper authentication (API keys, JWT, etc.).

## Data Isolation

Each user's data is completely isolated:

1. **Repository scoping**: `Neo4jContactRepository(driver, user_id)` filters all Cypher queries by owner Person with matching `user_id`
2. **Service isolation**: Each user gets their own `ContactService` instance with isolated pending state
3. **Flow state**: XState flow state is tracked per `(user_id, chat_id)` tuple
4. **No cross-user access**: No query or operation can access another user's contacts

## Future: Multi-Channel Identity

The architecture supports future multi-channel scenarios:

```
Alice's WhatsApp → ChannelLink(whatsapp, +1234567890) ─┐
Alice's Telegram → ChannelLink(telegram, 123456789)    ├→ Account(alice-uuid)
Alice's Web login → ChannelLink(web, alice@example.com)┘
```

All three channels would map to the same Account, giving Alice access to her contacts from any channel.

## Migration Notes

If you have old documentation or code that references "single-user", it should be updated to reflect the current multi-user architecture. Key files to update:

- ✅ `README.md` - Updated to mention multi-user
- ✅ `AGENTS.md` - Updated to mention multi-user
- ✅ `.cursor/notion_architecture_content.md` - Updated with identity layer and multi-user graph model
- ❓ `docs/PROJECT_CONTEXT.md` - If it exists, should be updated

## Testing Multi-User

To test multi-user behavior:

1. **Different Telegram accounts**: Open the bot from different Telegram accounts. Each should see only their own contacts.
2. **REST API with headers**: Use different `X-User-Id` headers to simulate different users.
3. **Verify isolation**: Add a contact as User A, list contacts as User B → User B should not see User A's contact.
