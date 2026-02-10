Problem description
People already know valuable people, but that knowledge is fragile: it lives in memory, chat histories, and intuition. When the opportunity to connect others arises, people often fail to act—not because they don’t want to help, but because they lack a clear, externalized understanding of who they know and why those relationships matter.
Most tools either try to introduce strangers or require heavy, structured data entry that interrupts natural behavior. As a result, capturing relationship context rarely happens at the moment it is freshest.
This MVP focuses on a single goal:
 allowing a user to quickly externalize a real, existing relationship—at the moment it matters—using a familiar communication interface, with minimal friction.

MVP scope
Single-user system (no authentication)


Telegram bot as the only interface


Contacts added only from Telegram contact cards


Context captured only at contact creation time


Free-text context as the primary source of meaning


No automation, discovery, or outbound actions



Core requirements
1. Contact creation (restricted input)
The system must allow contact creation only by:
Forwarding or sharing a Telegram contact card to the bot


The system must reject or ignore:
Manual text-only contact creation


Partial identifiers (name-only, username-only, phone-only)


For each contact, the system must store:
Internal unique ID


Name (from contact card)


Phone number (if provided by Telegram)


Telegram user ID (if available)


Timestamp of creation


Rationale
 This ensures:
Contacts are real


Minimal ambiguity


Low cognitive overhead for the user



2. Context capture (creation-time only)
Upon receiving a valid contact card, the system must:
Prompt the user to add free-text context describing the relationship


Context rules
Context is mandatory for contact creation


Context is added once, at creation time only


Context cannot be edited or appended later in this MVP


Context is stored as raw text without structure


Examples of valid context
“Frontend engineer, very strong in React, met at Chill & Chat”


“Friend from university, well connected in VC circles”


“Designer, great at UX research, very thoughtful intros”



3. Contact persistence
A contact is considered successfully created only when:
A valid contact card is received


Context is provided


If context is not provided:
The contact must not be stored


The operation is considered incomplete



4. Contact retrieval & search
The system must allow the user to:
Request a list of stored contacts


Search contacts by keywords found in the context text


Retrieve basic information for each contact:


Name


Context


Creation timestamp


Search behavior
Case-insensitive


Partial keyword matching


No ranking required (simple match is sufficient)



Explicitly out of scope
The MVP must not include:
Manual contact creation


Tagging or categorization systems


Context editing or versioning


Introduction intent or matching


Automated introductions


Multi-user support


Authentication or authorization


Public profiles or contact visibility


Any action involving contacting third parties



Telegram-specific edge cases & behaviors
Message-type handling
The system must gracefully handle the following Telegram inputs:
Text messages without contact cards


Respond with guidance on how to add a contact


Images


Ignore and inform the user that images are not supported


Voice notes


Ignore and prompt for a contact card


Videos / files / stickers


Ignore with a minimal, non-blocking message


Multiple attachments in one message


Process only the contact card if present, ignore the rest



Contact-related edge cases
User sends the same contact card multiple times
 → System should detect duplicates and inform the user.


Contact card is missing phone number or Telegram ID
 → Still accept if name is present.


Two contacts share the same name
 → System must treat them as distinct entities.


User sends multiple contact cards in a row
 → Bot must process them sequentially, one at a time.



Flow interruption cases
User sends a contact card but never sends context
 → Bot should wait or remind, but not store the contact.


User sends another contact card while context is pending
 → Bot should clarify which contact the context applies to.


User abandons the flow and returns later
 → No partial data should be persisted.



Error & resilience behavior
Bot restarts mid-flow
 → In-progress contact creation is lost safely.


Unexpected message format
 → Bot responds with a neutral fallback message.


User attempts unsupported actions repeatedly
 → Bot continues to guide without blocking.


Success criteria for this MVP
This MVP is successful if:
Adding a contact + context takes under 30 seconds


The process feels as easy as forwarding a message


Every stored contact has meaningful human-written context


The system reflects the user’s real network, not an aspirational one


You gain insight into how people naturally describe the value of relationships

Core user stories
US-1: Add a real contact with context
As a user,
 I want to forward a contact card to the bot and immediately describe why this person is relevant,
 so that I can externalize the value of a real relationship while it’s fresh.
Acceptance criteria
Contact can only be added via a Telegram contact card


Bot prompts for context immediately after receiving the contact


Context is mandatory


Contact is stored only after context is provided



US-2: Prevent incomplete contacts
As a user,
 I want the system to avoid saving contacts without context,
 so that my network remains intentional and meaningful.
Acceptance criteria
If no context is provided, the contact is not stored


User is informed that the process is incomplete


Partial data is discarded safely



US-3: Handle duplicate contacts
As a user,
 I want to be informed if I try to add a contact that already exists,
 so that I don’t accidentally duplicate people in my network.
Acceptance criteria
System detects duplicate contact cards


User is notified that the contact already exists


No new contact is created



Retrieval & reflection stories
US-4: List all stored contacts
As a user,
 I want to see a list of all my stored contacts,
 so that I can reflect on my network.
Acceptance criteria
Bot returns a list of contacts


Each entry shows name and context


Order can be simple (e.g. creation time)



US-5: Search contacts by context keywords
As a user,
 I want to search my contacts using keywords,
 so that I can quickly recall who might be relevant for a situation.
Acceptance criteria
Search matches keywords inside context text


Search is case-insensitive


Partial matches are supported



Telegram interaction & resilience stories
US-6: Guide user when no contact card is sent
As a user,
 I want clear guidance when I send a message that is not a contact card,
 so that I know how to properly add a contact.
Acceptance criteria
Bot responds with instructions when receiving plain text


No contact is created



US-7: Ignore unsupported message types gracefully
As a user,
 I want the bot to handle images, voice notes, and files without breaking the flow,
 so that mistakes don’t cause frustration.
Acceptance criteria
Images, voice notes, videos, stickers, and files are ignored


Bot replies with a brief, helpful message


System remains stable



US-8: Handle flow interruptions
As a user,
 I want the system to behave predictably if I abandon a contact creation flow,
 so that I don’t end up with inconsistent data.
Acceptance criteria
No partial contact is stored


If a new contact card is sent mid-flow, bot clarifies intent


System can safely reset the flow



Edge & clarity stories
US-9: Distinguish contacts with the same name
As a user,
 I want contacts with the same name to be treated as different people,
 so that my network accurately reflects reality.
Acceptance criteria
Each contact has a unique internal identifier


Same-name contacts are allowed


Context differentiates them



US-10: Operate as a single-user system
As a user,
 I want the system to work without login or accounts,
 so that I can focus on usage instead of setup.
Acceptance criteria
No authentication required


All contacts belong to a single user implicitly


No user-switching logic exists

Domain model — Bimoi
Core idea
Bimoi models intentional personal relationships.
 A relationship exists only when a person is known and meaningful context about that relationship is explicitly captured.
The system represents a personal social graph centered on a single individual, where each node corresponds to a real person the user knows, and each relationship is enriched with human-authored meaning rather than inferred signals.

Core entities
Person
A Person represents a real individual known by the user.
A person exists in the system only if:
They are explicitly added by the user


They are associated with a real-world contact


Key characteristics
A person has a stable identity within the system


A person may share a name with other people


A person has no intrinsic value without context


Attributes
Person ID (internal, unique)


Name


External identifiers (if available)


Creation timestamp



RelationshipContext
A RelationshipContext represents the user’s explicit understanding of why a person matters.
It is not a generic note, but a declarative statement of value and relevance.
A person cannot exist without a relationship context.
Key characteristics
Authored by the user


Free-form text


Captured at a specific moment in time


Immutable in the current model


Attributes
Context ID (internal, unique)


Textual description


Creation timestamp



Relationships between entities
Person — has — RelationshipContext
Each Person has exactly one RelationshipContext


Each RelationshipContext belongs to exactly one Person


This enforces intentionality:
Knowing someone without knowing why they matter is not modeled.

Aggregate boundaries
ContactAggregate
A ContactAggregate groups:
One Person


One RelationshipContext


The aggregate is created atomically:
Either both Person and RelationshipContext exist


Or neither exists


There are no partial or intermediate states in the domain.

System-level constraints
The model represents a single-user perspective


All persons exist relative to that user


There are no relationships between persons themselves


The system does not infer value or importance


All meaning is explicitly provided by the user



Excluded concepts (by design)
The domain explicitly does not include:
Social network effects


Mutual relationships


Strength or scoring of relationships


Tags or categorization


Time-based evolution of relationships


Introductions or matchmaking


Public or shared profiles


These concepts may exist in future models but are intentionally absent here.

Conceptual summary
At its core, Bimoi models a single, powerful idea:
A relationship only exists when meaning is made explicit.
Everything else — discovery, introductions, networks — can only be built on top of that foundation.

