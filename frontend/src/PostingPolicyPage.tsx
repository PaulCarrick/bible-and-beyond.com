import type { View } from './views'

interface PostingPolicyPageProps {
  onNavigate: (view: View) => void
  // The site's name as this domain shows it (Site settings, or domainTitle.ts).
  siteTitle: string
}

// The rules for Conversations and the Prayer Wall, and the member's consent to their posts being checked by an AI
// (added 2026-11-22 at the owner's request; "Check posts with AI" in CLAUDE.md). The notice above the Post and Reply
// buttons links here ("By posting, you agree to our Posting policy"). Keep it true when posting, the checks or the
// emails change (conversations.py, post_moderation.py). Like Privacy, it opens without logging in.
function PostingPolicyPage({ onNavigate, siteTitle }: PostingPolicyPageProps) {
  const link = (view: View, words: string) => (
    <button type="button" className="link-button" onClick={() => onNavigate(view)}>
      {words}
    </button>
  )
  return (
    <div className="welcome privacy-page">
      <h1>Posting policy</h1>
      <p className="privacy-updated">Last updated: November 22, 2026</p>

      <p>
        This policy applies to everything a member writes on {siteTitle}&rsquo;s Conversations board and Prayer Wall:
        posts, prayer requests and replies (together, &ldquo;posts&rdquo;). In it, &ldquo;we&rdquo; and
        &ldquo;us&rdquo; mean the people who run this site. <strong>By submitting a post, you agree to this policy</strong>,
        including the automated review described below. If you do not agree, please do not post.
      </p>

      <h2>1. What posts must not contain</h2>
      <p>Posts must not contain, link to or promote:</p>
      <ul>
        <li>profanity, obscene or crude language, or slurs;</li>
        <li>
          political messages: support for or opposition to political parties, candidates, office holders or political
          campaigns, or arguments about partisan political issues (praying for leaders, a nation or peace is welcome);
        </li>
        <li>
          advertising or spam: selling or promoting products, services, businesses or websites, or asking for money
          (mentioning a church, ministry, Bible study, support group or Christian resource is welcome);
        </li>
        <li>harassment, threats, insults aimed at people, or hate toward any group;</li>
        <li>sexual content, or encouragement of violence, self-harm or anything illegal;</li>
        <li>
          anyone else&rsquo;s personal information (such as an address, phone number or private details of their life)
          without their permission;
        </li>
        <li>material you do not have the right to share, such as copyrighted text, lyrics or pictures;</li>
        <li>anything else that is plainly inappropriate for a Christian community.</li>
      </ul>

      <h2>2. Automated review of posts, and your consent</h2>
      <p>
        When the site&rsquo;s administrators have turned it on, every new or changed post and reply is reviewed
        automatically before it is published. Its title and text (never your name or email address) are sent to{' '}
        <strong>Google&rsquo;s Gemini artificial-intelligence service</strong>, which judges whether it meets section 1.
        A post it finds unsuitable is not published, and you are told why so that you can change it.{' '}
        <strong>Private prayer requests, and replies to them, are never sent for review.</strong>
      </p>
      <p>
        <strong>
          By submitting a post, you consent to its text being sent to Google and analyzed by an automated system for
          this purpose.
        </strong>{' '}
        Google handles that text under its own terms and privacy policy, which may allow it to keep the text for a
        time. We do not keep the result of the review. Automated review can make mistakes in both directions: it may
        refuse a suitable post or let an unsuitable one through, and when the service cannot be reached a post may be
        published without review. If you believe a post was refused by mistake, write to us on the{' '}
        {link('contact', 'Contact')} page.
      </p>

      <h2>3. Review by people, and removal</h2>
      <p>
        The site&rsquo;s administrators can read every post, private prayer requests included. We may remove any post,
        and may withdraw a member&rsquo;s permission to post, at our discretion, with or without notice, when we
        believe it breaks this policy or harms the community. We are not obliged to review every post, and the
        absence of removal does not mean we approve of a post.
      </p>

      <h2>4. Who sees your posts</h2>
      <ul>
        <li>
          Posts and replies on Conversations and the Prayer Wall are <strong>public</strong>: anyone who can open this
          site can read them, with your name (or &ldquo;Anonymous&rdquo; when you choose to post anonymously).
        </li>
        <li>A private prayer request is seen only by you and the site&rsquo;s administrators.</li>
        <li>
          Posts may also be <strong>sent by email or text message</strong>: replies to the author who asked for them;
          new Conversations posts and replies to members the administrators have chosen to receive them; prayer
          requests to the prayer list or to a group or group leader you choose.
        </li>
      </ul>
      <p>
        Do not post anything you would not want others to read. Once a post has been read or emailed, deleting it
        cannot take it back from those who received it.
      </p>

      <h2>5. Your posts and your responsibility</h2>
      <p>
        You keep ownership of what you write. By posting, you give us a non-exclusive, royalty-free permission to
        store, display, copy (for example in backups) and send your post by email or text as this policy describes, for
        as long as it remains on the site. You may edit or delete your own posts at any time; copies may remain for a
        while in backups and in emails already sent.
      </p>
      <p>
        You are responsible for what you post, and you confirm that you have the right to post it. Posts express the
        views of their authors, not of {siteTitle} or of any church, and we do not check them for accuracy.
      </p>

      <h2>6. Not professional help</h2>
      <p>
        Conversations and the Prayer Wall are for fellowship and prayer, not counseling, medical, legal or other
        professional advice. <strong>If you or someone else is in danger, call 911.</strong> In the United States you
        can call or text <strong>988</strong> (the Suicide and Crisis Lifeline) at any time.
      </p>

      <h2>7. No warranty</h2>
      <p>
        The site, including Conversations, the Prayer Wall and the automated review, is provided free and &ldquo;as
        is&rdquo;. To the fullest extent the law allows, we make no promises about it and are not liable for any loss
        arising from posts written by members, from the removal or refusal of a post, or from the review&rsquo;s
        mistakes.
      </p>

      <h2>8. Questions, reports and changes</h2>
      <p>
        To report a post or ask about this policy, write to us on the {link('contact', 'Contact')} page. What we keep
        about you, and what is sent to outside services, is on our {link('privacy', 'Privacy')} page. We may change
        this policy; the date at the top shows when it last changed, and posting after a change means you accept the
        new version.
      </p>
    </div>
  )
}

export default PostingPolicyPage
