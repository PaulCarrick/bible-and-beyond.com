import type { ReactNode } from 'react'
import type { View } from './views'

interface PrivacyPageProps {
  onNavigate: (view: View) => void
  // The site's name as this domain shows it (Site settings, or domainTitle.ts).
  siteTitle: string
}

// What is sent to each outside service and when. Keep it true when a service is added or removed
// (see "Privacy page" in CLAUDE.md).
const outsideServices: { service: string; whatIsSent: ReactNode; when: string }[] = [
  {
    service: 'Google Gemini (AI)',
    whatIsSent:
      'The words of the question or search, or of a post or reply being checked: never your name or email address',
    when:
      'When you open an FAQ answer, ask your own question or use an AI search, and, when the site checks posts, when you post or reply in Conversations or on the Prayer Wall',
  },
  {
    service: 'Google reCAPTCHA',
    whatIsSent: 'Information about your browser and device, so Google can tell people from spam robots',
    when: 'On the Contact page only',
  },
  {
    service: 'Google Ads (Google Tag Manager)',
    whatIsSent: 'Which pages you visit, with Google’s cookies',
    when: 'On every page of the site',
  },
  {
    service: 'API.Bible',
    whatIsSent:
      'A report that a licensed Bible passage was shown, with a random number kept in your browser that does not identify you',
    when: 'When you view the NIV, NASB or The Message (their licence requires it)',
  },
  {
    service: 'Internet Archive',
    whatIsSent: 'Your search words, sent by our server, not by your browser',
    when: 'When you choose “Search the Internet Archive”',
  },
  {
    service: 'Telnyx (text messages)',
    whatIsSent: 'Your cell number and a short text (a devotional title, prayer request titles, a reply to your post, your verse a day, or a verse card someone sends you), and with picture messages the address of the picture',
    when: 'Only if you ticked “Send via SMS”; never otherwise',
  },
  {
    service: 'Our email provider',
    whatIsSent: 'Your email address and the message',
    when: 'Contact messages, account emails, daily devotionals, the verse a day, the prayer list, replies you asked to be emailed, and verse cards someone sends you',
  },
]

// The site's privacy and security statement (added 2026-11-15 at the owner's request; "Privacy" under About).
function PrivacyPage({ onNavigate, siteTitle }: PrivacyPageProps) {
  return (
    <div className="welcome privacy-page">
      <h1>Privacy and security</h1>
      <p className="privacy-updated">Last updated: November 26, 2026</p>
      <p>
        {siteTitle} is a non-commercial website. This page explains what we collect, who can see it, and what
        we send to other services.
      </p>

      <h2>Our promise</h2>
      <p>
        <strong>
          We do not sell your personal information, and we do not share or disclose it on purpose, except as
          described on this page or when the law requires it.
        </strong>
      </p>

      <h2>You do not need an account</h2>
      <p>You can read, search and listen without an account or any personal information.</p>

      <h2>What we keep if you set up an account</h2>
      <ul>
        <li>
          <strong>Your email address and password.</strong> We never store your password itself, only a scrambled
          version of it that cannot be turned back into the password. If you set up your account with a phone number
          instead of an email address, we keep that number to log you in, and text it only a code to confirm it, a
          password reset link you ask for, and the texts you choose.
        </li>
        <li>
          <strong>Your first name, last name and phone number,</strong> if you choose to give them. All three are
          optional. We keep whether you want your messages by email, by text or both, and as pictures; if you ask for
          text messages, we also keep when you agreed to them and whether you replied STOP.
        </li>
        <li>
          <strong>Your picture,</strong> if you add one on Account settings: a small square copy of the photo (any
          location or camera details in the file are dropped). It is shown only to you, in the account icon; it is
          deleted when you remove it or when your account is deleted.
        </li>
        <li>
          <strong>Picture messages,</strong> if you ask for them: each picture (a verse or a devotional&rsquo;s opening
          words over a photograph; nothing about you) is kept on our server for seven days at an address that cannot be
          guessed, so that the text message service can fetch it, and then deleted.
        </li>
        <li>
          <strong>Groups.</strong> A church leader who looks after a group of people (a deacon, say) can add you to their
          group on our administration pages, by your email address. If you have an account here, they see your name,
          address and phone and how you chose to get messages, and their messages reach you that way. If you do not,
          we keep the name, address and phone they typed, and send you their messages by email only. We keep what was
          sent and how many it reached, not to whom. Each of you gets your own copy, addressed to the leader: your
          address is never shown to the others in the group. Every group email has a link to stop that group&rsquo;s
          messages, and replies go to the leader. A leader can also schedule messages to go on a date or every week or
          month. If you choose to email a prayer request to your group or its leader, it goes to them with your name
          and your email address (so they can reply), and is private on the Prayer Wall.
        </li>
        <li>
          <strong>Your notes, playlists, lists and daily-email choices.</strong> Notes, playlists and the lists of search
          results you save are private to you.
        </li>
        <li>
          <strong>Your notes, pins and routes on the maps,</strong> if an administrator has let your account add them:
          the words you write and the places on the map they mark. They are private to you, except any you share: the
          members you choose by their email address see that one, with your name.
        </li>
        <li>
          <strong>One login cookie</strong> that keeps you logged in. It is needed for the site to work, lasts 30
          days, and is removed when you log out.
        </li>
      </ul>

      <h2>What other people can see</h2>
      <ul>
        <li>
          <strong>Conversations and Prayer Wall posts and replies are public.</strong> Anyone who visits the site
          can read them, including people without an account, and your first and last name are shown with each
          post. We ask search engines not to list those pages, but we cannot promise every search engine will
          follow that request. Please do not post anything you want to keep private.
        </li>
        <li>
          <strong>A Conversations post sent to one member</strong> is seen only by you, that member and the site
          owner and administrators. The first time you send to someone, they are told your name and asked whether to
          accept posts from you (by email or text, as they chose); nothing you wrote is shown to them until they
          accept. We keep their answer, and they can change it on their My account page.
        </li>
        <li>
          <strong>A verse card you send</strong> (Make your own card, on Verse of the day) shows the person who gets it
          your name, and replies go to your email address. When you send it to someone on the site, you see only their
          name, never their address or number. An address you type is used for that one email and is not kept.
        </li>
        <li>
          <strong>On the Prayer Wall you can choose.</strong> A request posted <em>anonymously</em> shows
          &ldquo;Anonymous&rdquo; instead of your name. A <em>private</em> request is seen only by you and the site owner
          and administrators, and is emailed only to them. A request you choose to <em>email to the prayer list</em> is sent,
          with your name unless it is anonymous, to everyone who signed up for the weekly prayer list email.
        </li>
        <li>
          <strong>The site administrators</strong> can see account details, and can read and remove posts, so
          they can run and protect the site. Their pages show how many notes, pins and routes you have on the maps,
          not what they say.
        </li>
      </ul>

      <h2>What we send to other services</h2>
      <div className="privacy-table-wrapper">
        <table className="privacy-table">
          <thead>
            <tr>
              <th scope="col">Service</th>
              <th scope="col">What is sent</th>
              <th scope="col">When</th>
            </tr>
          </thead>
          <tbody>
            {outsideServices.map((entry) => (
              <tr key={entry.service}>
                <th scope="row">{entry.service}</th>
                <td data-label="What is sent">{entry.whatIsSent}</td>
                <td data-label="When">{entry.when}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p>
        These companies handle what they receive under their own privacy policies. Google’s is at{' '}
        <a href="https://policies.google.com/privacy" target="_blank" rel="noopener noreferrer">
          policies.google.com/privacy
        </a>
        .
      </p>
      <p>
        <strong>About AI queries:</strong> we never put your name or email address in an AI request, and we do not
        log what you typed. We keep a copy of AI answers so we do not have to ask again, but the search itself is
        stored only as a scrambled code, not as words. Please do not type personal details into a question. When
        the site checks posts, each new or changed post or reply (but never a private prayer request or a post sent to one member) is sent to
        Gemini only to be checked for profanity, political messages and ads; we keep nothing of that check. The
        rules for posts are in our{' '}
        <button type="button" className="link-button" onClick={() => onNavigate('postingPolicy')}>
          Posting policy
        </button>
        .
      </p>

      <h2>Security</h2>
      <ul>
        <li>The whole site uses an encrypted connection (HTTPS).</li>
        <li>Passwords are stored only in scrambled form, and login cookies cannot be read by scripts on the page.</li>
        <li>Limits on requests slow down anyone trying to guess passwords or flood the site with spam.</li>
        <li>Backups are kept privately by the site owner.</li>
      </ul>
      <p>No website can promise perfect security, but we work to protect what you trust us with.</p>

      <h2>Your choices</h2>
      <ul>
        <li>You can stop devotional, verse a day, prayer list, reply or group emails with the link at the bottom of any email.</li>
        <li>
          You can stop text messages by replying STOP to any text, or by unticking <em>Send via SMS</em> on your My account page. Your
          mobile carrier may charge for texts you receive. The{' '}
          <button type="button" className="link-button" onClick={() => onNavigate('smsTerms')}>
            Text message terms
          </button>{' '}
          say what is sent and how often.
        </li>
        <li>
          You can close your account yourself at the foot of the My account page: it can no longer log in, and after one
          email saying it was closed we send you nothing more. What you stored is kept until you ask us to delete it. To
          delete your account and everything stored with it, to reopen it, or to ask what we hold about you, use the{' '}
          <button type="button" className="link-button" onClick={() => onNavigate('contact')}>
            Contact
          </button>{' '}
          page.
        </li>
        <li>
          You can block or delete cookies in your browser. The site still works without them, but you will not be
          able to log in.
        </li>
      </ul>

      <h2>Children</h2>
      <p>This site is not meant for children under 13, and we do not knowingly collect their information.</p>

      <h2>Changes</h2>
      <p>If we change this page, we will update the date at the top.</p>
    </div>
  )
}

export default PrivacyPage
