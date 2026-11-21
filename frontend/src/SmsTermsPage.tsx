import type { View } from './views'

interface SmsTermsPageProps {
  onNavigate: (view: View) => void
  // The site's name as this domain shows it (Site settings, or domainTitle.ts).
  siteTitle: string
}

// The terms of the text messages (added 2026-11-21 at the owner's request, for Telnyx's toll-free verification,
// which asks for a terms and conditions address): what is sent, how often, the costs, STOP and HELP. Keep it true
// when the texts change (sms.py, "Text messages" in CLAUDE.md). Like Privacy, it opens without logging in.
function SmsTermsPage({ onNavigate, siteTitle }: SmsTermsPageProps) {
  return (
    <div className="welcome privacy-page">
      <h1>Text message terms</h1>
      <p className="privacy-updated">Last updated: November 21, 2026</p>

      <h2>The program</h2>
      <p>
        {siteTitle} is a free, non-commercial Bible study website run by{' '}
        {siteTitle === 'Bible and Beyond' ? 'a nonprofit' : 'Bible and Beyond, a nonprofit'} in Washington State. Members who choose to can receive some of the site&rsquo;s notices as text messages (SMS, and MMS for
        pictures) instead of, or as well as, by email.
      </p>

      <h2>How you sign up</h2>
      <p>
        Texts are optional and never needed to use the site. To get them, give your US or Canadian cell number on the
        sign-up form or your{' '}
        <button type="button" className="link-button" onClick={() => onNavigate('account')}>
          My account
        </button>{' '}
        page, tick <em>This is a cell (mobile) number</em>, and tick <em>Send via SMS</em>. Ticking that box is your
        agreement to receive these texts. We then send one welcome text confirming it. Texts go only while your email
        address is confirmed.
      </p>

      <h2>What we send</h2>
      <ul>
        <li>The daily devotional reading you chose, if you asked for one.</li>
        <li>The verse a day, if you asked for it (as a picture if you ticked <em>Send Multimedia Messages</em>).</li>
        <li>The weekly prayer list, if you asked for it.</li>
        <li>A notice when someone replies to your post, if you asked for one.</li>
        <li>Messages from a group leader of a group you belong to on the site.</li>
      </ul>
      <p>
        Each text starts with the site&rsquo;s name, is short, usually has a link to the reading on this site, and ends
        with &ldquo;Reply STOP to end texts.&rdquo; We send no advertising, and we never sell or share your number for
        others&rsquo; marketing.
      </p>

      <h2>How often</h2>
      <p>
        Message frequency varies with what you chose: usually one to three texts a day, plus the weekly prayer list
        and any replies to your posts.
      </p>

      <h2>Costs</h2>
      <p>
        The texts are free from us. <strong>Message and data rates may apply</strong>: your mobile carrier may charge
        you for texts you receive, and picture texts (MMS) may cost more. Carriers are not liable for delayed or
        undelivered messages.
      </p>

      <h2>Stopping, starting and help</h2>
      <ul>
        <li>
          <strong>Reply STOP</strong> (or STOPALL, UNSUBSCRIBE, CANCEL, END, QUIT) to any text to stop all of them at
          once. We send one text confirming it and nothing more.
        </li>
        <li>
          <strong>Reply START</strong> to turn them back on (only if you had agreed to them before).
        </li>
        <li>
          <strong>Reply HELP</strong> to get a text saying what the texts are and how to change or stop them.
        </li>
        <li>
          You can also untick <em>Send via SMS</em> on your My account page at any time.
        </li>
      </ul>

      <h2>Who can get them</h2>
      <p>Texts are sent only to US and Canadian cell numbers. You must be the owner or authorized user of the number.</p>

      <h2>Privacy</h2>
      <p>
        What we keep about your number and your choice, and what we send to our text message provider, is on our{' '}
        <button type="button" className="link-button" onClick={() => onNavigate('privacy')}>
          Privacy
        </button>{' '}
        page.
      </p>

      <h2>Questions</h2>
      <p>
        Reply HELP to any text, or write to us on the{' '}
        <button type="button" className="link-button" onClick={() => onNavigate('contact')}>
          Contact
        </button>{' '}
        page.
      </p>

      <h2>Changes</h2>
      <p>If we change these terms, we will update the date at the top.</p>
    </div>
  )
}

export default SmsTermsPage
