# LineCheck Architecture v1.1

## Foundation, Vision, and Scalability Plan

### Restaurant-First, Multi-Industry by Design

**Version:** 1.1  
**Status:** Foundational product and technical direction  
**Initial market:** Restaurants, cafés, and hospitality operations  
**First deployments:** Little Luna, followed by Cafe Luna  
**Long-term direction:** A configurable, multi-tenant operations and workforce execution platform  
**Supersedes:** LineCheck Architecture v1.0

---

## 1. Document Intent

This document establishes the architectural direction for **LineCheck** before additional development creates assumptions that become difficult or expensive to reverse.

LineCheck will be built and validated first in restaurants because that is where the product has immediate access to real users, real operating conditions, and a clear set of problems to solve. Little Luna is the first operating environment, and Cafe Luna is the next expansion environment.

However, the underlying product must not assume that every future customer is a restaurant.

The same foundational system may eventually support organizations such as:

- Restaurants, cafés, bars, bakeries, and hospitality groups
- Security companies and contract guard operations
- Hotels, housekeeping teams, and facilities departments
- Retail stores and multi-site service businesses
- Warehouses, light manufacturing, and distribution operations
- Schools, nonprofits, and community organizations
- Hospitals and healthcare organizations for appropriate operational workflows
- Any organization coordinating recurring work, staff responsibilities, training, reviews, incidents, and location-based operations

The purpose of this architecture is to prevent two opposite problems:

1. **Building a Little Luna-only or restaurant-only application** that later requires a major rewrite to support other organizations, operating models, locations, or industries.
2. **Overengineering a universal enterprise platform too early**, slowing down the practical restaurant workflows LineCheck needs to solve today.

The intended balance is:

> **Build LineCheck for Little Luna now, make restaurants the first focused market, and ensure the underlying platform remains useful beyond restaurants.**

This is an architecture charter. It is not a requirement to immediately build public billing, healthcare compliance, enterprise infrastructure, every possible workflow, or every future integration. It defines the boundaries within which those capabilities can be added deliberately later.

---

## 2. Product Definition

LineCheck is an **operations and workforce execution platform**.

It helps an organization answer practical questions such as:

- What work needs to be done today?
- Who is allowed or expected to do it?
- Has it been completed correctly?
- What evidence or review is required?
- What work was missed, delayed, or returned?
- What does each employee need to learn?
- Who is working, where, and when?
- What issues, incidents, or maintenance needs were reported?
- What operational patterns should managers act on?

For restaurants, these concepts may appear as:

- Opening, mid-shift, and closing side work
- Deep-cleaning routines
- Manager assignments
- Food-safety or equipment checks
- Training modules and recipes
- Shift schedules
- Fix requests
- Completion reports and accountability

For another industry, the same platform foundations may appear differently:

- Security post orders, patrol checks, incident reports, and shift handoffs
- Retail opening and closing procedures, merchandising checks, and cash-handling verification
- Hotel room-readiness, housekeeping, maintenance, and inspection workflows
- Facilities rounds, equipment inspections, preventive maintenance, and safety tasks
- Healthcare environmental rounds, departmental checklists, equipment readiness, and staff training

The surface language and templates may change. The underlying platform concepts should remain stable.

---

## 3. Market Strategy: Focused First, Expandable by Design

### 3.1 The Beachhead Market

Restaurants and cafés are LineCheck's initial market and should remain the primary product focus during early development.

This provides:

- Direct access to real operating environments
- Fast feedback from staff and managers
- Repeated daily workflows that expose product weaknesses quickly
- Clear operational pain points
- A practical path from one location to multiple locations
- A coherent initial sales and marketing message

LineCheck should not dilute its early product by trying to satisfy every industry at once.

### 3.2 The Platform Opportunity

Restaurant workflows should be implemented as the first **vertical profile**, not as permanent assumptions embedded throughout the platform.

The long-term model is:

> **One operational core, multiple configurable industry profiles.**

The restaurant profile may define:

- Restaurant-specific terminology
- Opening, service, and closing templates
- Side-work categories
- Recipe and food-safety learning content
- Restaurant role presets
- Point-of-sale integrations
- Restaurant-focused reports

A security profile could later define:

- Site and post terminology
- Patrol and guard-tour workflows
- Incident-report templates
- Officer and supervisor role presets
- Site handoff procedures
- Security-specific integration options

The profile changes the configured experience. It does not create a separate LineCheck product or codebase.

---

## 4. Purpose

LineCheck will be developed and validated in stages:

1. **Little Luna first** — prove that LineCheck solves real daily operating problems.
2. **Cafe Luna next** — prove that a second operating environment can be added without duplicating or rewriting the application.
3. **Restaurant beta** — prove that LineCheck can be configured, supported, and sold to outside restaurant operators.
4. **Restaurant SaaS launch** — establish repeatable onboarding, subscriptions, integrations, and support.
5. **Adjacent-industry pilots** — validate that the operational core works outside restaurants through configuration rather than forks.
6. **Broader multi-industry expansion** — introduce additional industry profiles only after they are validated in real environments.

Foundational choices should be made now when they prevent meaningful future blockers. Feature development should continue without unnecessary architectural detours.

---

## 5. North Star

> **Build software that feels effortless for one small team, yet is powerful enough for a complex multi-site organization—all from one shared platform.**

For the initial market, that means software simple enough for an employee completing closing side work on a shared café tablet, while still supporting the controls required by managers, owners, installers, support personnel, and multi-location operators.

For future markets, the same principle should hold: frontline users see only the tools needed to perform their work, while the platform preserves strong permissions, modular workflows, reporting, integrations, and organizational control behind the scenes.

---

## 6. Guiding Principles

### 6.1 Build for Ten; Architect for Ten Thousand

LineCheck does not need infrastructure sized for ten thousand organizations today. It does need data models, authorization rules, module boundaries, and integration patterns that will not collapse when more tenants, users, locations, or industries are added.

This means:

- Avoid premature infrastructure complexity.
- Do not hard-code Little Luna-specific behavior into shared business logic.
- Do not hard-code restaurant-only concepts where a broader operational concept exists.
- Require tenant and operational-unit context in organization-owned data.
- Establish stable internal service boundaries.
- Build repeatable configuration rather than customer-specific forks.
- Preserve a clear path to stronger infrastructure when actual scale requires it.

The objective is **scalable design**, not premature scale.

---

### 6.2 One Product, One Codebase, Many Tenants

LineCheck should operate as one shared product with:

- One primary codebase
- One maintained product architecture
- One deployable application per environment
- One common platform core
- Tenant-specific configuration, branding, access, modules, terminology, and integrations

Development, staging, and production will remain separate environments, but each production release should serve all compatible tenants from the same maintained product.

LineCheck should not create:

- A Little Luna edition
- A Cafe Luna edition
- A restaurant codebase and a security codebase
- Separate branches for individual customers
- Customer-specific application deployments unless a future enterprise requirement genuinely justifies them

Tenant and industry differences should be expressed through:

- Configuration
- Permissions
- Entitlements
- Terminology
- Templates
- Workflow policies
- Integration settings
- Vertical profiles

They should not be expressed through permanent code forks.

---

### 6.3 One Operational Core, Multiple Vertical Profiles

The platform should use stable, industry-neutral concepts internally while allowing the user-facing product to use familiar industry terminology.

Examples:

| Core Platform Concept | Restaurant Profile | Security Profile | Facilities Profile |
|---|---|---|---|
| Organization | Restaurant company or group | Security company | Facilities organization |
| Operational Unit | Location | Client site or post | Building, campus, or department |
| Team Member | Staff member | Officer or guard | Technician or team member |
| Routine Work | Side work | Post checks or patrol tasks | Inspection or maintenance rounds |
| Issue | Fix request | Incident or escalation | Maintenance request |
| Work Evidence | Completion photo or note | Patrol evidence or incident detail | Inspection reading or photo |
| Supervisor | Shift lead or manager | Site supervisor | Department or facilities supervisor |

The application may display the terminology appropriate to the tenant's profile. The core authorization and data model should not depend on those labels.

---

### 6.4 Keep the Interface Simple; Keep the Backend Modular

Frontline users should not see the complexity of the platform architecture.

A restaurant employee may only need:

- Home
- Routine
- Learn
- Shift
- More

A security officer might use the same product structure with different labels or configured modules.

Behind those simple surfaces, the backend should maintain clear modules for:

- Identity
- Authorization
- Recurring work
- Assignments
- Evidence
- Reviews
- Notifications
- Learning
- Scheduling
- Issues and incidents
- Integrations
- Reporting
- Auditing
- Tenant administration

Complexity belongs behind the interface, not inside the frontline experience.

---

### 6.5 Roles Define Permissions; Plans Unlock Modules

LineCheck must distinguish between separate access questions:

1. **Is this tenant entitled to use the module?**
2. **Is this user an active member of the tenant?**
3. **Is this user allowed to perform the action?**
4. **Is the user allowed to act within this organizational unit?**
5. **Does the resource itself permit the action in its current state?**

For example:

- A tenant's plan may include Scheduling.
- A site manager may have permission to publish a schedule.
- A supervisor may be allowed to edit only an unpublished schedule.
- A team member may only be allowed to view published shifts.

A user must pass all relevant checks.

A useful authorization formula is:

> **Access = authenticated user + active tenant membership + operational scope + permission + module entitlement + resource rule + current workflow state**

Roles must not become scattered collections of hard-coded checks such as:

```text
if user is manager...
```

Instead:

- Roles are named permission bundles.
- Permissions represent individual capabilities.
- Entitlements determine which modules are available.
- Scope determines where a permission applies.
- Resource rules determine whether the action is valid for a particular record.
- Workflow state determines whether the action is currently allowed.

---

### 6.6 Tenant Data Is Completely Isolated

Every organization must operate as a private tenant.

“Completely isolated” means one tenant must never be able to view, modify, search, export, infer, or accidentally receive another tenant's information.

This applies at every layer:

- Application queries
- API endpoints
- Background jobs
- Search
- Exports
- File storage
- Notifications
- Analytics
- Audit logs
- Integrations
- Support access
- Caches
- Generated reports
- AI-assisted features, if introduced later

Physical database separation is not required for every tenant at the start. A shared database can be appropriate if tenant scoping is rigorous and supported by defense-in-depth safeguards. Dedicated databases or deployments may remain an enterprise option later.

---

### 6.7 Prefer Plug-In-Style Integrations

External services should connect through standardized adapters or connectors.

Examples may include:

- Toast or other point-of-sale systems
- Twilio or other messaging providers
- Transactional email providers
- Payroll or human-resources systems
- Calendar providers
- Learning-content providers
- Guard-tour or security systems
- Maintenance platforms
- Identity providers
- Future public API consumers

Core LineCheck workflows should not depend directly on one provider's implementation.

For example, the notification module should request:

> “Send this team member a shift-change notification.”

It should not need to know whether the message is delivered through SMS, email, push notification, or another provider.

---

### 6.8 Regulated Capabilities Must Be Explicit, Not Assumed

LineCheck may eventually support operations in regulated industries, including healthcare, security, food service, or other environments with heightened privacy, safety, labor, or recordkeeping requirements.

The architecture should preserve the ability to add appropriate controls, but the platform must not claim or assume regulatory compliance merely because it can be configured for an industry.

For example:

- Hospital operational workflows may be supported without storing patient information.
- Clinical data or protected health information should not enter the platform unless a separately governed capability is deliberately designed, secured, contracted, and validated for that purpose.
- Payment-card information should remain with dedicated payment providers rather than being stored directly by LineCheck.
- Industry-specific retention, approval, signature, or evidence requirements should be implemented through explicit policies and modules.

The rule is:

> **Support regulated environments through deliberate scope and controls; never inherit regulated data obligations accidentally.**

---

## 7. Platform Model

### 7.1 Multi-Tenant SaaS Structure

The primary tenant is an **Organization**.

An organization can contain one or more **Operational Units**. An operational unit may represent a:

- Restaurant location
- Café
- Store
- Building
- Department
- Campus
- Warehouse
- Client site
- Security post
- Team
- Region
- Other managed operating boundary

The initial restaurant experience may use the word **Location**, but the platform model should remain broad enough to support other unit types.

```text
LineCheck Platform
└── Organization / Tenant
    ├── Operational Units
    │   ├── Locations
    │   ├── Sites
    │   ├── Departments
    │   ├── Teams
    │   └── Optional parent-child hierarchy
    ├── Users and Memberships
    ├── Roles and Permissions
    ├── Settings and Terminology
    ├── Module Entitlements
    ├── Vertical Profile
    ├── Integrations
    ├── Templates and Workflows
    ├── Audit History
    └── Subscription and Billing Relationship
```

The organizational-unit structure should permit a controlled hierarchy without requiring every tenant to use one.

Examples:

```text
Restaurant Group
├── Little Luna
└── Cafe Luna
```

```text
Security Company
├── Downtown Office Contract
│   ├── Lobby Post
│   └── Overnight Patrol
└── Warehouse Contract
```

```text
Hospital Organization
├── Main Campus
│   ├── Environmental Services
│   └── Facilities
└── Outpatient Building
```

The platform should support both simple and complex tenants without forcing a small business to configure an enterprise hierarchy.

---

### 7.2 Core Platform Entities

The foundational model should include concepts similar to the following:

| Entity | Responsibility |
|---|---|
| **User** | A person's global LineCheck identity |
| **Organization** | The tenant and primary security boundary |
| **Operational Unit** | A location, site, department, team, post, or other operating scope |
| **Membership** | Connects a user to an organization |
| **Unit Access** | Defines which operational units a member may access |
| **Membership Type** | Classifies the relationship, such as employee, contractor, volunteer, or external collaborator |
| **Role** | A named collection of permissions |
| **Permission** | A granular action the user may perform |
| **Module** | A product capability such as Routine, Learn, or Scheduling |
| **Entitlement** | Enables a module, limit, or capacity for a tenant |
| **Vertical Profile** | Provides industry terminology, presets, and configuration defaults |
| **Work Template** | Defines reusable operational work |
| **Work Occurrence** | Represents a scheduled or issued instance of work |
| **Assignment or Participation Record** | Defines who may or must perform the work |
| **Evidence or Submission** | Records proof, notes, photos, values, or responses |
| **Review Record** | Records approval, rejection, return, or verification |
| **Issue Record** | Represents a fix request, incident, concern, escalation, or maintenance need |
| **Learning Content** | Defines training, procedures, reference material, or assessments |
| **Integration** | Connects a tenant to an outside service |
| **Audit Event** | Records an important action or access event |
| **Subscription** | Represents the tenant's commercial plan and billing state |

A user identity should be able to belong to more than one organization without requiring duplicate accounts.

---

### 7.3 Organizational Hierarchy Rules

Operational units may have parent-child relationships, but hierarchy must not become an uncontrolled substitute for permissions.

Recommended rules:

- Every organization has at least one root operational context.
- A small tenant may operate with one organization and one location only.
- A unit may inherit selected settings from a parent.
- Permissions may be scoped to the organization, a unit, a unit subtree, a team, or an individual resource.
- Inheritance must be explicit and testable.
- A child unit may override only settings that the platform marks as overridable.
- Moving a unit within the hierarchy must not silently expose data to new users.

The hierarchy should support expansion without forcing complexity onto Little Luna.

---

## 8. Platform Roles

Platform roles exist outside a tenant's normal workforce hierarchy.

### 8.1 Super Administrator

Full platform-level access for a very limited number of trusted operators.

Capabilities may include:

- Creating, suspending, and restoring organizations
- Managing platform plans and entitlements
- Reviewing platform health
- Managing platform administrators
- Investigating severe incidents
- Accessing protected support tools
- Managing global configuration

Super administrator access should never be used for ordinary tenant operations.

### 8.2 Installer or Onboarding Specialist

Responsible for configuring new organizations and operational units.

Capabilities may include:

- Creating an organization
- Adding locations, sites, departments, or teams
- Selecting a vertical profile
- Importing templates
- Connecting integrations
- Assisting with initial user setup
- Testing configuration
- Moving the tenant into active status

This role should not automatically receive unrestricted permanent access to tenant data.

### 8.3 Support

Provides controlled assistance to a tenant.

Support access should be:

- Time-limited
- Purpose-specific
- Restricted to the necessary tenant and scope
- Approved or initiated through a defined process
- Fully audited
- Revocable immediately
- Visibly distinguishable from normal tenant activity

Sensitive support access should operate like a controlled **support session**, not an invisible permanent back door.

---

## 9. Tenant Roles

### 9.1 Neutral Role Model

The platform should begin with neutral role templates such as:

| Core Role Template | General Responsibility |
|---|---|
| **Tenant Owner** | Organization oversight, configuration, billing, and high-level reporting |
| **Organization Administrator** | Broad administrative control without necessarily owning billing |
| **Unit Manager** | Operational control for one or more assigned units |
| **Supervisor or Team Lead** | Limited team, shift, or workflow leadership |
| **Team Member** | Completes work, views assigned information, and submits evidence |
| **Limited Collaborator** | Performs narrowly scoped work without normal employee access |

These are default permission bundles, not permanent limitations.

### 9.2 Restaurant Profile Labels

For the restaurant profile, the same role model may be presented as:

| Restaurant Label | Core Role Template |
|---|---|
| Owner | Tenant Owner |
| General Manager | Organization Administrator or senior Unit Manager |
| Manager | Unit Manager |
| Shift Lead | Supervisor or Team Lead |
| Staff | Team Member |

### 9.3 Other Industry Labels

A security profile may use labels such as:

- Company Administrator
- Account Manager
- Site Supervisor
- Shift Supervisor
- Officer

A facilities profile may use:

- Director
- Facilities Manager
- Department Supervisor
- Lead Technician
- Technician

The labels may change. Authorization remains permission-based.

### 9.4 Custom Roles

A tenant may eventually need custom roles such as:

- Training Coordinator
- Kitchen Manager
- Regional Manager
- Safety Officer
- Maintenance Lead
- Human Resources Administrator
- Compliance Reviewer
- Read-Only Auditor

The permission model should support custom roles without changing how core authorization works.

---

## 10. Permission Model

Permissions should represent specific actions, such as:

- View
- Create
- Edit
- Delete
- Complete
- Claim
- Release
- Assign
- Reassign
- Approve
- Verify
- Return for correction
- Publish
- Archive
- Restore
- Configure
- Manage members
- Manage roles
- View reports
- Export data
- Manage integrations
- View billing
- Manage billing
- Open support access
- View sensitive evidence
- Manage retention policies

Permissions must also be scoped.

Possible scopes include:

- Self
- Assigned work
- Team
- Operational unit
- Operational-unit subtree
- Entire organization
- Specific resource
- Platform

Examples:

- View Routine work at one restaurant location
- Publish Learn content across an organization
- Manage employees only at assigned sites
- View reports without viewing billing
- Reassign work without editing the underlying template
- Review incident reports without viewing unrelated personnel records
- Configure an integration only for a specific operational unit

The interface may hide unavailable controls, but the server must independently authorize every protected action. Hiding a button is not security.

---

## 11. Work Participation Model

LineCheck's operational-work model should remain usable across industries.

The current participation patterns are broadly applicable:

### Shared

Any eligible team member may complete all or part of the work without claiming exclusive ownership.

Restaurant example: A shared closing checklist completed by two employees.

Facilities example: A department cleanup checklist completed collaboratively.

### Claimable

An eligible team member claims responsibility before beginning durable work.

Restaurant example: A deep-cleaning task claimed by one employee.

Security example: An available patrol assignment claimed by an eligible officer.

### Assigned

The work is restricted to one or more specifically designated people, roles, or teams.

Restaurant example: A manager assigns an equipment inventory to one employee.

Healthcare-operations example: A department readiness check is assigned to a designated facilities technician.

These participation rules should remain core platform behavior rather than restaurant-specific logic.

---

## 12. Product Modules and Subscription Structure

The subscription structure below is illustrative. It is not a final pricing commitment.

| Plan | Illustrative Modules |
|---|---|
| **Free** | Routine, basic operational work, and Learn |
| **Starter** | Free features plus Assignments and Notifications |
| **Pro** | Starter features plus Scheduling, Analytics, and Reporting |
| **Enterprise** | Multi-unit administration, API access, advanced integrations, specialized controls, and priority support |

Internal pilot tenants may receive manually assigned entitlements without being attached to a public billing plan.

### 12.1 Recommended Module Catalog

LineCheck should treat the following as modular capabilities:

- **Core Platform** — identity, organizations, units, memberships, roles, permissions, audit
- **Routine** — recurring operational work and daily execution
- **Assignments** — persistent or one-time work issued to people or teams
- **Issues** — fixes, incidents, concerns, maintenance needs, requests, and escalations
- **Learn** — training, procedures, reference material, assessments, and acknowledgment
- **Shift** — scheduling, availability, shift information, and handoffs
- **Notifications** — in-app, email, SMS, push, and future channels
- **Analytics and Reporting** — operational performance, completion, trends, and accountability
- **Integrations** — provider connectors, synchronization, and external events
- **Billing and Entitlements** — plans, limits, trials, subscriptions, and module access
- **Administration and Support** — tenant setup, support sessions, configuration, and platform oversight

The restaurant interface may continue to call the Issues module **Fixes**. Another profile may call it **Incidents**, **Maintenance**, or **Requests**.

---

## 13. Separate Four Different Controls

LineCheck should not treat every feature switch as the same thing.

### 13.1 Entitlement

Determines whether the tenant is contractually or administratively allowed to use a module or capacity.

Example: The Pro plan includes Analytics.

### 13.2 Feature Flag

Controls technical rollout, experimentation, or safety.

Example: Analytics v2 is enabled for Little Luna while it is being tested.

### 13.3 Tenant Setting

Represents an organization's operating choice.

Example: Little Luna requires manager review for closing Routine work.

### 13.4 Vertical Profile

Provides industry-oriented terminology, templates, defaults, and configuration presets.

Example: The restaurant profile uses “Side Work,” enables opening and closing template presets, and recommends Toast as an available integration.

These four controls must remain distinct. Combining them would tangle billing, deployment safety, customer preferences, and industry presentation.

---

## 14. Vertical Configuration Framework

### 14.1 Purpose

A vertical profile adapts LineCheck to an industry without forking the platform.

A profile may define:

- Display terminology
- Default roles
- Starter templates
- Workflow presets
- Suggested evidence types
- Default reports
- Recommended integrations
- Dashboard emphasis
- Industry-specific form fields
- Optional policy packs

A profile must not bypass core security, authorization, tenant isolation, or audit requirements.

### 14.2 Configuration Hierarchy

A useful configuration hierarchy is:

```text
Platform defaults
└── Vertical profile defaults
    └── Organization settings
        └── Operational-unit settings
            └── Template settings
                └── Individual work occurrence
```

Lower levels may override only the settings intentionally marked as overridable.

### 14.3 Example Profiles

| Profile | Example Workflows | Example Terminology | Example Integrations |
|---|---|---|---|
| **Restaurant** | Opening, side work, closing, deep cleaning, food-safety checks | Location, staff, shift lead, side work, fix | POS, scheduling, SMS, email |
| **Security** | Post orders, patrols, handoffs, incident reports, equipment checks | Client site, post, officer, supervisor, incident | Guard-tour, scheduling, messaging |
| **Facilities** | Inspections, preventive maintenance, cleaning rounds, work requests | Building, department, technician, work order | Maintenance systems, sensors, messaging |
| **Retail** | Opening, closing, merchandising, inventory checks, cash-control procedures | Store, associate, key holder, task, issue | POS, inventory, scheduling |
| **Hospitality** | Room-readiness, housekeeping, inspections, guest-service recovery | Property, department, attendant, inspection | Property-management, maintenance, messaging |
| **Healthcare Operations** | Environmental rounds, equipment readiness, training, departmental checks | Campus, department, team member, readiness check | Identity, maintenance, approved messaging |

Healthcare operational use should default to workflows that do not require patient data. Any future regulated-data capability requires separate governance and validation.

### 14.4 No Per-Tenant Custom Code

A tenant may configure its workflows, terminology, templates, roles, and settings. It should not receive a private code branch.

When a customer requests something unique, the decision should be:

1. Can configuration already express it?
2. Is it a reusable capability that belongs in the shared platform?
3. Is it an optional module or profile extension?
4. Is it outside LineCheck's product boundary?

The answer should not default to customer-specific code.

---

## 15. Recommended Application Architecture

The best fit for LineCheck is a **modular monolith**.

This means LineCheck remains one deployable application, but its internal domains are separated into clearly owned modules.

Recommended modules include:

- Core Platform
- Identity and Access
- Organization and Operational-Unit Management
- Routine
- Assignments
- Issues and Incidents
- Learn
- Shift and Scheduling
- Notifications
- Analytics and Reporting
- Integrations
- Billing and Entitlements
- Vertical Profiles and Terminology
- Administration and Support
- Audit, Security, and Compliance Controls

A modular monolith provides:

- Faster development
- Simpler deployment
- Easier testing
- One release process
- Strong internal consistency
- Lower operational overhead
- A practical path to future service extraction

LineCheck should not introduce microservices merely to appear scalable. A module should become a separate service only when measurable operational, security, performance, or deployment requirements justify the added complexity.

Modules should communicate through stable internal services or domain events rather than directly modifying one another's private data.

---

## 16. Core Domain Language

New internal architecture should prefer stable, neutral domain language.

Recommended canonical terms include:

- Organization
- Operational Unit
- User
- Membership
- Role
- Permission
- Module
- Entitlement
- Vertical Profile
- Work Template
- Work Occurrence
- Work Item
- Participation
- Assignment
- Evidence
- Submission
- Review
- Issue
- Learning Content
- Shift
- Integration
- Audit Event

Restaurant-specific terms may remain in the restaurant user experience:

- Side Work
- Opening
- Mid-Shift
- Closing
- Deep Cleaning
- Staff
- Shift Lead
- Fix
- Recipe

This does not require an immediate disruptive rename of every existing database table or code symbol. Existing implementation should be evaluated carefully and migrated only where the long-term benefit exceeds the risk. The critical requirement is that new architecture does not deepen restaurant-only assumptions.

---

## 17. Tenant-Isolation Requirements

Every tenant-owned record should include an organization identifier. Unit-specific records should also include an operational-unit identifier where applicable.

Examples include:

- Work templates
- Work occurrences
- Work items
- Assignments
- Claims
- Completion records
- Evidence
- Comments
- Reviews
- Issues and incidents
- Learning content
- Schedules
- Notifications
- Memberships
- Reports
- Integration records
- Audit events
- Files and media references

Required safeguards include:

1. All tenant queries are automatically scoped to the authenticated organization.
2. Client-provided organization identifiers are never trusted without membership validation.
3. Operational-unit access is checked independently of tenant membership.
4. Database uniqueness rules include the tenant boundary where appropriate.
5. Background jobs carry explicit organization and unit context.
6. File paths and object storage are partitioned by tenant.
7. Search indexes preserve tenant boundaries.
8. Exports cannot combine tenants unintentionally.
9. Cached data preserves tenant context.
10. Notifications cannot resolve recipients across tenant boundaries accidentally.
11. Analytics aggregation respects tenant and unit scope.
12. Cross-tenant access tests are part of automated acceptance.
13. Database row-level security may be used as an additional defense where supported.
14. Tenant context must never be inferred from a globally unique record identifier alone.
15. Support access must use an explicit, audited tenant context.

A particularly important test is:

> A valid user from Organization A attempts to access a valid record belonging to Organization B and receives no information about its existence.

---

## 18. Integration Framework

Every integration should implement a common connector contract where practical.

A connector may provide operations such as:

- Authenticate
- Test connection
- Refresh credentials
- Import
- Export
- Synchronize
- Receive webhooks
- Map external identifiers
- Report health
- Retry failed operations
- Disconnect safely
- Revoke credentials
- Reconcile conflicting records

### 18.1 Credential Management

External credentials must be:

- Stored per tenant
- Scoped to the necessary operational units when applicable
- Encrypted at rest
- Excluded from logs
- Restricted to the integration service
- Rotatable
- Revocable
- Audited when changed
- Never packaged into source code, tenant exports, or development fixtures

### 18.2 Reliability

Integrations should support:

- Idempotent processing
- Retry policies
- Exponential backoff
- Duplicate-event protection
- Failure visibility
- Manual resynchronization
- Last-successful-sync status
- Tenant-specific health reporting
- Dead-letter or failure-review handling where appropriate
- Safe handling of partial imports
- Reconciliation after outages

Provider-specific behavior should remain inside its connector.

Toast-specific behavior belongs in the Toast connector. Twilio-specific behavior belongs in the Twilio connector. A future security or facilities provider should follow the same pattern.

---

## 19. Security and Trust Principles

### 19.1 Tenant Isolation

No cross-tenant access, including accidental access through search, logs, cached data, files, background processing, generated reports, or integrations.

### 19.2 Least Privilege

Users, platform administrators, services, background workers, and integrations receive only the access required for their responsibilities.

### 19.3 Secure Secret Storage

Passwords, API keys, tokens, signing secrets, and provider credentials are stored through protected secret-management mechanisms.

### 19.4 Server-Side Authorization

Every protected mutation and sensitive read is authorized on the server.

### 19.5 Auditability

Important actions should be recorded with:

- Actor
- Tenant
- Operational unit
- Action
- Target
- Timestamp
- Before-and-after context when appropriate
- Permission or support-session context
- Request or correlation identifier
- Result
- Relevant source, device, or integration context when appropriate

### 19.6 Controlled Support Access

Platform support cannot silently enter tenant accounts. Support access must be bounded, attributable, and visible in audit history.

### 19.7 Secure Defaults

New modules, integrations, permissions, and sensitive data categories should default to unavailable until intentionally enabled.

### 19.8 Data Classification

LineCheck should distinguish between data categories such as:

- Public configuration
- Internal operational data
- Personnel data
- Sensitive evidence
- Credentials and secrets
- Regulated or specially governed data

Access, retention, exports, and logging should reflect the classification.

### 19.9 Data Lifecycle Controls

The architecture should support:

- Export
- Retention
- Archival
- Deactivation
- Deletion
- Legal or administrative holds where appropriate
- Tenant-specific retention policies
- Secure media cleanup
- User offboarding

### 19.10 Compliance Is a Product Capability, Not a Marketing Assumption

LineCheck may pursue certifications, contractual controls, or industry-specific compliance later. Those claims should be made only after the required technical, legal, administrative, and operational controls are actually in place.

---

## 20. Direct Implications for the Current LineCheck Build

This architecture should guide current work without stopping the roadmap.

### 20.1 Routine

Routine should be understood internally as recurring operational work.

The restaurant profile may continue to present:

- Opening
- Mid-shift
- Closing
- General side work
- Deep cleaning

All Routine templates, occurrences, items, claims, completion records, evidence, comments, review actions, and historical records must be tenant-scoped.

Shared, Claimable, and Assigned participation remain core domain rules. They should not be duplicated in restaurant-specific logic.

Daily resets and schedule calculations should use the operational unit's configured timezone.

### 20.2 Assignments

Assignments should support persistent or one-time work issued to:

- An individual
- Multiple individuals
- A role
- A team
- An operational unit
- Any eligible participant

The restaurant experience may describe these as additional side work or manager assignments. The core model should remain broader.

### 20.3 Issues, Fixes, and Incidents

The existing **Fixes** experience should be treated as one presentation of a broader Issue domain.

An issue may represent:

- A broken item
- A maintenance request
- A safety concern
- An operational problem
- A customer-service recovery item
- An incident
- A policy exception
- A supply need
- A manager escalation

The restaurant profile may continue to use **Fixes** where that wording is clear and approachable.

### 20.4 Learn

Learn content should support:

- Organization-wide material
- Operational-unit material
- Role-based audiences
- Team-based audiences
- Publication permissions
- Required and optional learning
- Completion records
- Acknowledgment
- Assessments
- Versioned procedures

Restaurant content may include recipes, service standards, opening procedures, food-safety material, and employee handbooks. Other verticals may use different content without changing the Learn architecture.

### 20.5 Shift and Scheduling

Scheduling should distinguish between:

- Organization membership
- Operational-unit eligibility
- Role permissions
- Employee availability
- Skills or qualifications when introduced
- Schedule publication rights
- Shift visibility
- Handoff requirements

The model should work for restaurant shifts, security posts, facilities coverage, and other scheduled operations.

### 20.6 Notifications

Core modules should request notifications through a shared notification service rather than calling Twilio, email, or push providers directly.

Notification policy may vary by tenant, unit, urgency, event type, user preference, and subscription entitlement.

### 20.7 Analytics and Reporting

Reports should be based on stable operational concepts, including:

- Work completion
- Timeliness
- Missed work
- Review outcomes
- Participation
- Reassignments
- Issue volume
- Training completion
- Shift coverage
- Unit trends

Restaurant-specific dashboards may emphasize opening and closing performance. Other profiles may emphasize patrol completion, inspection results, maintenance response, or training compliance.

### 20.8 Administration

Tenant administration and platform administration must remain separate.

A tenant owner is not automatically a LineCheck platform administrator.

A tenant administrator should manage only authorized users, units, settings, templates, integrations, and reports within the tenant.

### 20.9 Existing Little Luna Configuration

Little Luna-specific names, identifiers, templates, schedules, categories, branding, role labels, and integration credentials belong in tenant configuration or tenant data—not shared application logic.

### 20.10 Current Code and Schema Review

As development continues, new and modified components should be reviewed for restaurant-only assumptions such as:

- Hard-coded `restaurant_id` where `organization_id` is intended
- Hard-coded `location` where a broader operational unit is required
- Role checks tied only to restaurant titles
- Universal use of “side work” for all work types
- Universal use of “fix” for incidents or requests
- Restaurant-only notification text embedded in services
- Toast assumptions embedded outside the Toast connector
- Required menu or recipe concepts inside the Learn core

Existing working code should not be rewritten indiscriminately. Foundational refactors should be small, tested, documented, and tied to a concrete architectural benefit.

---

## 21. Development Stance

LineCheck should continue feature development in manageable roadmap slices.

The team should:

- Make small foundational refactors early when they prevent real future debt.
- Preserve restaurants as the primary product focus during early validation.
- Keep the platform core industry-neutral where practical.
- Treat restaurant vocabulary as profile-level presentation when it is not a universal concept.
- Avoid broad rewrites based only on hypothetical scale.
- Introduce tenant context as a required system boundary.
- Centralize permissions before more modules create inconsistent authorization.
- Build connectors when external services are introduced.
- Preserve working behavior through migration and acceptance testing.
- Keep architecture documentation synchronized with implementation decisions.
- Validate new abstractions against real workflows rather than abstract possibility.

The team should not:

- Pause all product progress to build a universal enterprise control plane.
- Attempt to launch multiple industries simultaneously.
- Introduce microservices without measurable need.
- Build public billing before external beta requires it.
- Create separate customer or industry codebases.
- Embed subscription checks throughout unrelated UI components.
- Add abstract flexibility that makes normal workflows harder to use.
- Claim regulated-industry readiness before the appropriate controls exist.
- Turn LineCheck into a full ERP, payroll system, point-of-sale system, clinical record system, or public-safety dispatch system.

LineCheck should integrate with specialized systems rather than trying to replace every system an organization uses.

---

## 22. Roadmap Framing

### Phase One — Little Luna Validation

#### Objective

Prove the core workflows in a real restaurant environment.

#### Priorities

- Routine reliability
- Shared-tablet usability
- Shared, Claimable, and Assigned work
- Manager review
- Learn
- Shift
- Administration
- Tenant-scoped records
- Central permissions
- Location timezone correctness
- Audit history
- Operational stability
- Restaurant terminology and templates

#### Exit Standard

Little Luna can operate LineCheck daily without product logic that assumes it is the only organization or location in the system.

---

### Phase Two — Cafe Luna Expansion

#### Objective

Prove that another operating environment can be onboarded through configuration rather than code duplication.

#### Priorities

- Repeatable organization and location setup
- Reusable restaurant templates
- Separate employee populations
- Location-level permissions
- Independent settings and integrations
- Cross-location management where authorized
- Onboarding workflow
- Import and migration tools
- Tenant- and location-specific reporting
- Validation of the organization and operational-unit model

#### Exit Standard

Cafe Luna can be added without creating a fork, duplicating the application, or exposing Little Luna data.

This phase is the first practical test of the multi-tenant architecture.

---

### Phase Three — External Restaurant Beta and Billing

#### Objective

Operate LineCheck for restaurant customers who do not share the original development relationship.

#### Priorities

- Assisted external onboarding
- Restaurant profile packaging
- Subscription records
- Plan entitlements
- Billing integration
- Support-access controls
- Tenant exports
- Product analytics
- Service monitoring
- Error reporting
- Documentation
- Terms, privacy, and operational policies
- Repeatable customer configuration

#### Exit Standard

An outside restaurant can be onboarded, configured, supported, billed, and removed through repeatable platform processes.

---

### Phase Four — Restaurant SaaS Launch

#### Objective

Offer LineCheck as a reliable commercial platform for restaurants and hospitality operators.

#### Priorities

- Reliable signup and onboarding
- Subscription lifecycle automation
- Upgrade and downgrade behavior
- Multi-location administration
- Restaurant integrations
- Platform observability
- Backup and recovery procedures
- Security review
- Customer support systems
- Commercial documentation
- Service-level objectives

#### Exit Standard

LineCheck can acquire and support new restaurant customers without direct development intervention for every account.

---

### Phase Five — Adjacent-Industry Pilots

#### Objective

Prove that the operational core works outside restaurants without a separate codebase.

The first adjacent vertical should be selected based on access to a real operating partner, not theoretical market size alone. Security, facilities, hospitality, retail, or another operationally similar environment may be appropriate.

#### Priorities

- Select one adjacent vertical
- Define its terminology profile
- Configure role presets
- Build starter workflow templates
- Identify genuinely missing core capabilities
- Keep industry-specific behavior inside a profile or optional module
- Validate onboarding and reporting
- Document all changes required by the pilot

#### Exit Standard

A non-restaurant organization can use LineCheck through configuration and shared platform improvements, without a private fork or broad rewrite.

---

### Phase Six — Multi-Industry Expansion

#### Objective

Expand LineCheck deliberately into additional industries after the core model has been validated.

#### Priorities

- Additional vertical profiles
- Profile marketplace or template catalog, if justified
- Industry-specific connectors
- Configurable forms and evidence
- Advanced organizational hierarchies
- Qualification and credential tracking, if required
- Sector-specific retention and approval policies
- Public API and integration ecosystem
- Enterprise deployment options where justified

#### Exit Standard

LineCheck can serve multiple operational industries while preserving one coherent platform, one security model, and one maintained product architecture.

---

## 23. Feature Decision Filter

Before implementing a meaningful feature, the team should ask:

### 23.1 Tenant Boundary

Who owns this data: the platform, an organization, an operational unit, a team, or an individual?

### 23.2 Operational Scope

Does the feature apply to one location, one site, a department, a team, a unit subtree, or the whole organization?

### 23.3 Authorization

What exact permission is required, and at what scope?

### 23.4 Module Ownership

Which module owns the rule and the underlying record?

### 23.5 Entitlement

Is the module universally available or controlled by a plan, limit, or contract?

### 23.6 Configuration Type

Is this:

- Core product behavior?
- A feature flag?
- A tenant setting?
- A vertical-profile default?
- A template-level rule?

### 23.7 Industry Assumption

Is this behavior truly universal, or is it specific to restaurants or another vertical?

If it is vertical-specific, can it live in terminology, configuration, a template, a connector, or an optional module?

### 23.8 Integration

Does an external provider need an adapter rather than a direct dependency?

### 23.9 Data Sensitivity

Does the feature introduce personnel, credential, regulated, biometric, financial, health, or other specially governed data?

### 23.10 Auditability

Does the action need a durable record of who performed it, where, when, and under what authority?

### 23.11 Scalability

Can another organization use this without changing the code?

### 23.12 Migration

Can existing tenants adopt the change without losing history or behavior?

### 23.13 User Experience

Does the architecture remain invisible and effortless to the frontline user?

### 23.14 Product Boundary

Does this belong in LineCheck, belong in an integration, or belong in another specialized system?

When the answer to “Will this support another tenant or vertical without a rewrite?” is no, the design should be reconsidered before implementation.

---

## 24. Decisions to Lock Early

The following choices should be established relatively early because later changes would be expensive:

1. Organization and operational-unit hierarchy
2. Global user identity and tenant membership model
3. Required tenant context for organization-owned data
4. Central server-side authorization service
5. Role and permission structure
6. Permission scope model
7. Module entitlement model
8. Separation of entitlements, feature flags, tenant settings, and vertical profiles
9. Industry-neutral core domain language
10. Tenant-scoped file storage
11. Audit-event structure
12. Per-tenant integration credentials
13. Connector interface conventions
14. Operational-unit timezone ownership
15. Cross-tenant security tests
16. Modular-monolith boundaries
17. Data classification and sensitive-data boundaries
18. Controlled platform-support access
19. Configuration inheritance rules
20. No-fork policy for tenants and verticals

---

## 25. Decisions That Can Wait

The following do not need to block current product development:

- Final public pricing
- Exact plan names
- Billing-provider selection
- Self-service signup
- Final list of future industries
- Final terminology for every vertical
- Dedicated databases for enterprise customers
- Microservice extraction
- Public API design
- International data residency
- White-labeling
- Custom enterprise contracts
- Advanced usage-based billing
- Marketplace integrations
- Clinical or regulated healthcare-data support
- Industry certifications not required for the restaurant launch
- Advanced hierarchy beyond the needs of validated customers

These should remain possible without being built prematurely.

---

## 26. Non-Goals

This architecture does not mean LineCheck should immediately become:

- A generic project-management platform
- A full human-resources information system
- A payroll processor
- A point-of-sale system
- An electronic health record
- A public-safety dispatch platform
- A building-automation system
- A custom consulting codebase for every customer
- A collection of disconnected industry products

LineCheck's core purpose is operational execution: coordinating people, recurring work, assignments, learning, schedules, evidence, review, issues, and accountability.

Specialized systems should be connected through integrations when appropriate.

---

## 27. Architecture Success Standard

The architecture is working when:

- Little Luna receives a simple, purpose-built restaurant experience.
- Cafe Luna can be added without copying the codebase.
- A user can belong to more than one organization safely.
- An organization can contain one or many operational units.
- Every tenant-owned record has an enforceable tenant boundary.
- Permissions are consistent across modules and industries.
- Restaurant terminology does not control the core data model.
- Plans enable modules without rewriting workflows.
- Vertical profiles adapt terminology and defaults without creating forks.
- External providers can be replaced or expanded through connectors.
- Support access is temporary and auditable.
- New tenants require configuration rather than development.
- A non-restaurant pilot can be launched without a broad rewrite.
- Product development remains fast enough to respond to real frontline needs.
- The application remains easy for a small team even as platform capability grows.

---

## 28. Final Interpretation

The intent of **LineCheck Architecture v1.1** is not to build software for every industry today.

It is to make sure the restaurant product being built today becomes the legitimate first version of a broader operations platform rather than a technical dead end.

Little Luna should receive a focused restaurant tool, not a generic enterprise interface. Its employees should see familiar language such as Routine, Side Work, Learn, Shift, and Fixes. Its managers should receive restaurant-relevant templates, reports, and integrations.

At the same time, the underlying system should understand that:

- Little Luna is an organization or operating unit within a tenant structure.
- Its employees are tenant members with scoped permissions.
- Its work is represented through reusable operational concepts.
- Its restaurant terminology comes from a restaurant profile.
- Its integrations belong to the tenant.
- Its data is isolated.
- Its workflows can evolve without becoming universal assumptions.

The central architectural commitment is:

> **Move quickly on the restaurant roadmap, but never make “only restaurants will use this” a hidden assumption in the foundation.**

A suitable canonical location for this document is:

```text
docs/architecture/LINECHECK-ARCHITECTURE-V1.1.md
```
