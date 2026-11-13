# Handling a privacy request

What to do when a player asks to have their name corrected, their email removed, or their name removed from the site. The public explanation is the **Privacy** page on the site (`web/src/pages/Privacy.tsx`); keep the two in step.

Requests arrive through the feedback form as a public GitHub issue titled "Privacy request", with the person's email forwarded to the alert inbox. **Reply by email, never on the issue**, and close the issue without adding personal details to it.

Aim to finish within a month of the request.

## 1. Confirm who is asking

Ask, by email, which player name the request is about and what they want. If the request is to remove a name, a reasonable check is enough (for example, the email matches one on file, or they can name an event they played). Do not ask for identity documents.

## 2. Find the player

Open the player's page on the site and note the **player id** from the URL (`/players/<id>`). Check the Settings page for aliases that point to the same person.

## 3. Do what was asked

### Correct a name

Rename the player, then reload the site's data:

```
python3 -m scripts.rename_player_display --player-id <id> --to "Correct Name" --dry-run --db-env prod
python3 -m scripts.rename_player_display --player-id <id> --to "Correct Name" --apply --db-env prod
```

Read the line that prints the target database before trusting the output. The site keeps decks in memory, so afterwards restart the app so it reloads them: `railway restart -s metagameAnalyzer -e production` (a few seconds of downtime).

### Remove an email

On the player's page, clear the email field and save. The change log records that an email was removed, not the address.

### Remove a name from the site

1. **Remove the email** as above.
2. **Replace the name with a neutral label**, for example `Removed player <id>`:
   ```
   python3 -m scripts.rename_player_display --player-id <id> --to "Removed player <id>" --apply --db-env prod
   ```
3. **Stop a re-scrape from bringing the name back.** A scrape reads the real name from mtgtop8 again. Mark the player field of that player's decks as hand-edited so scrapes leave it alone (run against the production database):
   ```sql
   UPDATE decks
      SET manual_fields = COALESCE(manual_fields, '[]'::jsonb) || '["player"]'::jsonb
    WHERE player_id = <id>
      AND NOT COALESCE(manual_fields, '[]'::jsonb) ? 'player';
   ```
4. **Remove aliases** that contain the real name, on the Settings page. The alias list is public.
5. **Restart the app** as above and check the player page, one of their events and the Players list.

Tell the person what cannot be changed here: the original tournament pages (mtgtop8.com, league sites) and any GitHub issue text they wrote themselves.

## 4. What lingers, and for how long

| Where | How long | Notes |
|---|---|---|
| Event snapshots | up to 90 days | Admin-only. Restoring an old snapshot would bring the old name and email back for that event: after a removal, do not restore snapshots taken before it without redoing steps 1–3. |
| Change log | 180 days | Summaries may contain the old name (never an email). |
| Database backups (point-in-time recovery) | about 4 weeks | Only used to restore the whole database. After such a restore, redo any removal made since the restore point. |
| Server logs | Railway's retention | Request paths and IP addresses. |

Keep a private note of removals (player id and date, not the name) so they can be redone after a database restore.

## 5. Reply

Confirm by email what was done and what lingers, using the table above. Close the GitHub issue with "Handled by email."
