<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Form;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\Core\Datetime\DateFormatterInterface;
use Drupal\Core\Form\FormBase;
use Drupal\Core\Form\FormStateInterface;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * Adds an account to the main site, or changes one (its visitors' accounts, not Drupal users).
 *
 * The Python tool checks everything again (the address, the password rules, a clash with another
 * account); the checks here only give quicker messages.
 */
class SiteUserForm extends FormBase {

  /**
   * The same limits as setting up an account on the site (accounts.py).
   */
  private const PASSWORD_MINIMUM = 8;

  private const PASSWORD_MAXIMUM = 128;

  private const NAME_MAXIMUM = 100;

  private const PHONE_MAXIMUM = 40;

  public function __construct(
    protected BibleManager $manager,
    protected DateFormatterInterface $dateFormatter,
  ) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'), $container->get('date.formatter'));
  }

  public function getFormId(): string {
    return 'bible_admin_site_user';
  }

  public function buildForm(array $form, FormStateInterface $form_state, ?int $user_id = NULL): array {
    $form['#cache'] = ['max-age' => 0];
    // Shows the "Confirm password" box from the start (the admin theme hides it until the first box is typed in).
    $form['#attributes']['class'][] = 'site-user-form';
    $form['#attached']['library'][] = 'bible_admin/site_user_form';
    $user = NULL;
    if ($user_id !== NULL) {
      try {
        $user = $this->manager->getSiteUser((int) $user_id);
      }
      catch (BibleManagerException $exception) {
        $this->messenger()->addError($exception->getMessage());
        $form['back'] = ['#type' => 'link', '#title' => $this->t('Back to the site users'), '#url' => Url::fromRoute('bible_admin.site_users')];
        return $form;
      }
      $form_state->set('user_id', (int) $user['id']);

      $facts = [
        $this->t('Set up: @date', ['@date' => $this->formatDate($user['created_at'])]),
        $user['last_login_at'] ? $this->t('Last login: @date', ['@date' => $this->formatDate($user['last_login_at'])]) : $this->t('Never logged in'),
        $this->formatPlural((int) $user['note_count'], 'One note', '@count notes'),
        $this->formatPlural((int) $user['subscription_count'], 'One daily devotional email', '@count daily devotional emails'),
      ];
      $form['facts'] = ['#theme' => 'item_list', '#items' => $facts];
    }

    $form['email'] = [
      '#type' => 'email',
      '#title' => $this->t('Email address'),
      '#default_value' => $user['email'] ?? '',
      '#maxlength' => 254,
      '#description' => $this->t('The visitor logs in with it. It is kept in lower case. It may be left empty when a cell phone number is given below: the account then logs in with that number and is never emailed (no devotional or prayer list emails, no reply emails).'),
    ];
    $form['first_name'] = [
      '#type' => 'textfield',
      '#title' => $this->t('First name'),
      '#default_value' => $user['first_name'] ?? '',
      '#maxlength' => self::NAME_MAXIMUM,
    ];
    $form['last_name'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Last name'),
      '#default_value' => $user['last_name'] ?? '',
      '#maxlength' => self::NAME_MAXIMUM,
      '#description' => $this->t('Visitors give their names when they set up an account; accounts set up before the names were asked for have none. Here they may be left empty.'),
    ];
    $form['phone'] = [
      '#type' => 'tel',
      '#title' => $this->t('Phone'),
      '#default_value' => $user['phone'] ?? '',
      '#maxlength' => self::PHONE_MAXIMUM,
      '#description' => $this->t('Optional when there is an email address; needed without one (a US or Canadian cell number, which the account then logs in with). A US number is kept as +1 (555) 123-4567. Changing it turns off this member\'s text messages unless Texts on is ticked below.'),
    ];
    // Texts (sms_opt_in, with Send via SMS; added 2026-11-22 at the owner's request). The member's own consent is
    // needed: the box says so, and turning it on sends the welcome text that tells them how to stop.
    $stopped = !empty($user['sms_stopped']) && empty($user['sms_opt_in']);
    $form['texts'] = [
      '#type' => 'checkbox',
      '#title' => $this->t('Texts on (they agreed to get text messages)'),
      '#default_value' => $user['sms_opt_in'] ?? FALSE,
      '#description' => $this->t('Sends this member their notices by text (as Send via SMS on their My account page does). Tick it only when they have told you they want texts: carriers require their consent. The phone must be a US or Canadian cell number. Turning it on texts them a welcome message saying how to stop (reply STOP).')
        . ($stopped ? ' ' . $this->t('<strong>They replied STOP to our texts.</strong> Turn them on again only if they asked; their carrier may still block them until they reply START.') : ''),
    ];
    $form['email_verified'] = [
      '#type' => 'checkbox',
      '#title' => $this->t('Email address confirmed'),
      '#default_value' => $user['email_verified'] ?? FALSE,
      '#description' => $this->t('The daily devotional emails are only sent to a confirmed address. A visitor confirms it by following the link we email them; tick this only if you know the address is theirs.'),
    ];
    // For an account that logs in with its phone (2026-11-17): like "Email address confirmed", for the number.
    $form['phone_verified'] = [
      '#type' => 'checkbox',
      '#title' => $this->t('Phone number confirmed'),
      '#default_value' => $user['phone_verified'] ?? FALSE,
      '#description' => $this->t('For an account that logs in with its phone number (one with no email address). Texts, such as the verse a day and group messages, go only to a confirmed number. A visitor confirms it by typing the code we text them; tick this only if you know the number is theirs.'),
      '#states' => ['visible' => [':input[name="email"]' => ['value' => '']]],
    ];
    if (!empty($user['login_phone']) && ($user['email'] ?? '') !== '') {
      // An account that has both: it logs in either way, so the box shows whatever the address.
      unset($form['phone_verified']['#states']);
    }
    $form['open_ai_queries'] = [
      '#type' => 'checkbox',
      '#title' => $this->t('Open AI queries'),
      '#default_value' => $user['open_ai_queries'] ?? FALSE,
      '#description' => $this->t('Lets this visitor ask their own questions of the AI on the FAQ page (when logged in). Off unless turned on here.'),
    ];
    $form['use_conversations'] = [
      '#type' => 'checkbox',
      '#title' => $this->t('Conversations'),
      '#default_value' => $user['use_conversations'] ?? FALSE,
      '#description' => $this->t('Lets this visitor read, write and search the members\' posts on the Conversations page (when logged in). Off unless turned on here.'),
    ];
    $form['use_maps'] = [
      '#type' => 'checkbox',
      '#title' => $this->t('Maps: own notes, pins and routes'),
      '#default_value' => $user['use_maps'] ?? FALSE,
      '#description' => $this->t('Lets this visitor add their own notes, pins and routes to the maps (when logged in), and share them with other members who have this ticked. Off unless turned on here.'),
    ];
    $form['share_lists'] = [
      '#type' => 'checkbox',
      '#title' => $this->t('Can share lists'),
      '#default_value' => $user['share_lists'] ?? FALSE,
      '#description' => $this->t('Lets this visitor share their lists (My lists) on the Public lists page under Members, where everyone who can use the site sees them. Turning it off hides their shared lists. Off unless turned on here.'),
    ];
    // Every new Conversations post and reply by email (added 2026-11-22 at the owner's request).
    $form['get_conversation_posts'] = [
      '#type' => 'checkbox',
      '#title' => $this->t('Get Conversation Posts'),
      '#default_value' => $user['get_conversation_posts'] ?? FALSE,
      '#description' => $this->t('Emails this visitor every new post and every new reply in Conversations (not the Prayer Wall), except their own. Needs a confirmed email address; each email has a link that turns it off. Off unless turned on here.'),
    ];
    $form['see_private_prayers'] = [
      '#type' => 'checkbox',
      '#title' => $this->t('Gets private prayer requests'),
      '#default_value' => $user['see_private_prayers'] ?? FALSE,
      '#description' => $this->t('For the site\'s own administrators: when this visitor gets the weekly prayer list email, it also holds the week\'s private Prayer Wall requests. Off unless turned on here.'),
    ];
    // An account its owner closed on My account (added 2026-11-17): untick to reopen it.
    if ($user !== NULL) {
      $form['closed'] = [
        '#type' => 'checkbox',
        '#title' => $this->t('Account closed'),
        '#default_value' => !empty($user['closed']),
        '#description' => !empty($user['closed'])
          ? $this->t('Closed by its owner on @date (My account > Close my account). It cannot log in and gets no emails or texts; everything in it is kept. Untick to reopen it, or use Delete to remove it with everything in it.', ['@date' => $this->formatDate((string) $user['closed_at'])])
          : $this->t('A closed account cannot log in and gets no emails or texts; everything in it is kept. Members close their own on My account.'),
      ];
    }
    // The Drupal administrator account this site account belongs to (added 2026-11-26): the administrator's
    // saved verse cards (My cards) are offered on a group's Send a message. Without one chosen, a Drupal account
    // is matched to the site account with the same email address.
    if ($user !== NULL) {
      $administrators = [0 => (string) $this->t('- None: matched by email address -')];
      foreach (\Drupal::entityTypeManager()->getStorage('user')->loadByProperties(['status' => 1]) as $account) {
        if ($account->id()) {
          $administrators[(int) $account->id()] = $account->getDisplayName() . ($account->getEmail() ? ' (' . $account->getEmail() . ')' : '');
        }
      }
      $form['drupal_uid'] = [
        '#type' => 'select',
        '#title' => $this->t('Drupal administrator account'),
        '#options' => $administrators,
        '#default_value' => (int) ($user['drupal_uid'] ?? 0),
        '#description' => $this->t('The admin account of the same person, if they have one. Their saved verse cards (My cards on the site) can then be attached to a group\'s Send a message. With none chosen, an admin account is matched to the site account with the same email address. One site account for each admin account.'),
      ];
    }
    $form['password'] = [
      '#type' => 'password_confirm',
      '#title' => $user === NULL ? $this->t('Password') : $this->t('New password'),
      // The two boxes have their own labels (Password, Confirm password), so the heading above them is only
      // for screen readers.
      '#title_display' => 'invisible',
      '#required' => $user === NULL,
      '#size' => 30,
      '#description' => $user === NULL
        ? $this->t('@min to @max characters. It is not emailed to the visitor, so tell them privately.', ['@min' => self::PASSWORD_MINIMUM, '@max' => self::PASSWORD_MAXIMUM])
        : $this->t('Leave both empty to keep the present password. A new one (@min to @max characters) logs the visitor out on every device.', ['@min' => self::PASSWORD_MINIMUM, '@max' => self::PASSWORD_MAXIMUM]),
    ];

    $form['actions'] = ['#type' => 'actions'];
    $form['actions']['submit'] = [
      '#type' => 'submit',
      '#value' => $user === NULL ? $this->t('Add the account') : $this->t('Save'),
      '#button_type' => 'primary',
    ];
    $form['actions']['cancel'] = [
      '#type' => 'link',
      '#title' => $this->t('Cancel'),
      '#url' => Url::fromRoute('bible_admin.site_users'),
      '#attributes' => ['class' => ['button']],
    ];
    return $form;
  }

  public function validateForm(array &$form, FormStateInterface $form_state): void {
    if (trim((string) $form_state->getValue('email')) === '' && trim((string) $form_state->getValue('phone')) === '') {
      $form_state->setErrorByName('email', $this->t('Give an email address or a cell phone number (or both).'));
    }
    foreach (['first_name', 'last_name', 'phone'] as $field) {
      if (preg_match('/[\x00-\x1f\x7f]/', (string) $form_state->getValue($field))) {
        $form_state->setErrorByName($field, $this->t('This must be one line of plain text.'));
      }
    }
    $password = (string) $form_state->getValue('password');
    if ($password === '') {
      return;
    }
    $length = mb_strlen($password);
    if ($length < self::PASSWORD_MINIMUM || $length > self::PASSWORD_MAXIMUM) {
      $form_state->setErrorByName('password', $this->t('The password must be @min to @max characters.', ['@min' => self::PASSWORD_MINIMUM, '@max' => self::PASSWORD_MAXIMUM]));
    }
    if (str_contains($password, "\n") || str_contains($password, "\r")) {
      $form_state->setErrorByName('password', $this->t('The password cannot contain a line break.'));
    }
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    $userId = $form_state->get('user_id');
    $email = trim((string) $form_state->getValue('email'));
    $password = (string) $form_state->getValue('password');
    $emailVerified = (bool) $form_state->getValue('email_verified');
    $openAiQueries = (bool) $form_state->getValue('open_ai_queries');
    $useConversations = (bool) $form_state->getValue('use_conversations');
    $seePrivatePrayers = (bool) $form_state->getValue('see_private_prayers');
    $useMaps = (bool) $form_state->getValue('use_maps');
    $shareLists = (bool) $form_state->getValue('share_lists');
    $getConversationPosts = (bool) $form_state->getValue('get_conversation_posts');
    $texts = (bool) $form_state->getValue('texts');
    $profile = [
      'first_name' => trim((string) $form_state->getValue('first_name')),
      'last_name' => trim((string) $form_state->getValue('last_name')),
      'phone' => trim((string) $form_state->getValue('phone')),
    ];
    try {
      if ($userId === NULL) {
        $user = $this->manager->createSiteUser($email, $password, $emailVerified, $openAiQueries, $useConversations, $seePrivatePrayers, $profile, $useMaps, (bool) $form_state->getValue('phone_verified'), $shareLists, $getConversationPosts, $texts);
        $this->messenger()->addStatus($this->t('Added the account @email.', ['@email' => $user['email'] ?: $user['phone']]));
      }
      else {
        $user = $this->manager->updateSiteUser((int) $userId, $email, $password, $emailVerified, $openAiQueries, $useConversations, $seePrivatePrayers, $profile, $useMaps, (bool) $form_state->getValue('closed'), (bool) $form_state->getValue('phone_verified'), $shareLists, $getConversationPosts, $texts, (int) $form_state->getValue('drupal_uid'));
        $this->messenger()->addStatus($password === ''
          ? $this->t('Saved @email.', ['@email' => $user['email'] ?: $user['phone']])
          : $this->t('Saved @email with the new password; it has been logged out everywhere.', ['@email' => $user['email'] ?: $user['phone']]));
      }
    }
    catch (BibleManagerException $exception) {
      // Stay on the form, with what was typed, so it can be corrected.
      $this->messenger()->addError($exception->getMessage());
      $form_state->setRebuild();
      return;
    }
    $form_state->setRedirect('bible_admin.site_users');
  }

  private function formatDate(string $iso): string {
    $time = strtotime($iso);
    return $time === FALSE ? '' : $this->dateFormatter->format($time, 'short');
  }

}
