import { Link } from 'react-router-dom'

const sectionTitle = { margin: '1.5rem 0 0.5rem', fontSize: '1.15rem' } as const
const paragraph = { color: 'var(--text)', lineHeight: 1.6, margin: '0 0 0.75rem' } as const

/**
 * What the site stores about players and how to ask for a correction or removal.
 * Keep it in step with docs/PRIVACY_REQUESTS.md (what the site owner does when asked).
 */
export default function Privacy() {
  return (
    <div className="page" style={{ maxWidth: 720, margin: '0 auto' }}>
      <h1 className="page-title">Privacy</h1>
      <p style={paragraph}>
        This is a hobby site that collects Magic: The Gathering tournament results so players can look at the
        metagame. It has no accounts for visitors, no advertising and no tracking cookies.
      </p>

      <h2 style={sectionTitle}>What this site stores about players</h2>
      <ul style={{ ...paragraph, paddingLeft: '1.25rem' }}>
        <li>
          <strong>Your name as it appears in tournament results</strong>, with your deck lists, placings and match
          results. Most of this is copied from public tournament pages (mtgtop8.com and league pages). The rest is
          entered by tournament organisers, or by you, through a one-time link.
        </li>
        <li>
          <strong>Your email address, only if the site owner added it</strong> to send you a link for uploading a
          deck or reporting results. It is never shown on the site, never included in exports others can download,
          and used for nothing else. Emails are delivered through an email provider (Brevo).
        </li>
      </ul>

      <h2 style={sectionTitle}>What happens when you use the site</h2>
      <ul style={{ ...paragraph, paddingLeft: '1.25rem' }}>
        <li>
          The server keeps short-lived technical logs of requests, including the IP address, to keep the site
          running and to limit abuse.
        </li>
        <li>Card images and mana symbols load from Scryfall, which therefore sees your browser&apos;s request.</li>
        <li>
          If you send feedback, its title and description become a public issue on the project&apos;s GitHub page.
          An email address you add to the form is passed to the site owner privately and is not published.
        </li>
        <li>
          Changes made through a one-time link are recorded (which link, when, and what changed) so mistakes can be
          undone.
        </li>
      </ul>

      <h2 style={sectionTitle}>Asking for a correction or removal</h2>
      <p style={paragraph}>
        You can ask to have your name corrected, your email removed, or your name removed from the results shown
        here. Use the <Link to="/feedback">feedback form</Link>: choose &quot;Other&quot;, write
        &quot;Privacy request&quot; as the title, and put your email address in the email field so the site owner
        can reply to you.
      </p>
      <p style={paragraph}>
        Remember that the title and description of a feedback message are public. Do not write your name or other
        personal details there; the site owner will ask for what is needed by email.
      </p>
      <p style={paragraph}>
        When a name is removed, it is replaced by a neutral label in every result on this site. Copies held in
        backups and in the site&apos;s private undo and change history disappear on their own within about six
        months. This site cannot change the tournament pages the results were copied from.
      </p>
    </div>
  )
}
