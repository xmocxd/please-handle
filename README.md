# please-handle

Discord bot for shared task lists, assignments, and scheduled reminders.

Setup and deploy: see [deploy.md](deploy.md).

## Slash commands

### Tasks (everyone)

| Command | Description | Options |
|---------|-------------|---------|
| `/tasklist` | Print the full public task list (unassigned + each assignee) | — |
| `/opentasks` | Print only the unassigned task list | — |
| `/hidelist` | Delete the most recent tracked public task list posts | — |
| `/announcetasks` | Force the outstanding-tasks announcement now | — |
| `/newtask` | Add a new unassigned task | `description` |
| `/removetask` | Delete a task from the unassigned list | `task_number` |
| `/pickup` | Pick up an unassigned task | `task_number` |
| `/drop` | Drop one of your assigned tasks back to unassigned | `task_number` |
| `/assign` | Assign an unassigned task to a user | `task_number`, `user` |
| `/unassign` | Unassign a task from a user's list | `user`, `task_number` |
| `/mytasks` | Show your assigned tasks (ephemeral) | — |
| `/markdone` | Mark one of your assigned tasks complete | `task_number` |

### Config (`/handle` — privileged)

Server owner and users listed in `PRIVILEGED_USERS`.

| Command | Description | Options |
|---------|-------------|---------|
| `/handle enable` | Enable scheduled posts in this channel | — |
| `/handle disable` | Disable scheduled posts in this channel | — |
| `/handle schedule` | Set a schedule | `type` (`opentasks` \| `announce`), `days` (e.g. `MTWHFSU`), `time` (`HHMM`) |
| `/handle timezone` | Set guild timezone | `tz` (IANA, e.g. `America/New_York`) |
| `/handle purge` | Set purge age for completed tasks | `age_in_days` |
| `/handle force-purge` | Purge all completed tasks now | — |
| `/handle settings` | Print current settings | — |
| `/handle recent-purged` | Show recently purged tasks | — |
| `/handle test no-tasks-announce` | Post the no-outstanding-tasks announce in this channel | — |

**Schedule defaults:** `opentasks` daily at `1100`; `announce` Mondays at `1200` (guild timezone). Day letters: `M T W H F S U` (Mon–Sun; `H` = Thursday, `U` = Sunday).
