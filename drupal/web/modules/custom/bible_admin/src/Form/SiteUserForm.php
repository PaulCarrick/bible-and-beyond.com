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
  private const PASSWORD_MINIMUM = 10;

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
      '#required' => TRUE,
      '#maxlength' => 254,
      '#description' => $this->t('The visitor logs in with it. It is kept in lower case.'),
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
      '#description' => $this->t('Optional.'),
    ];
    $form['email_verified'] = [
      '#type' => 'checkbox',
      '#title' => $this->t('Email address confirmed'),
      '#default_value' => $user['email_verified'] ?? FALSE,
      '#description' => $this->t('The daily devotional emails are only sent to a confirmed address. A visitor confirms it by following the link we email them; tick this only if you know the address is theirs.'),
    ];
    $form['open_ai_queries'] = [
      '#type' => 'checkbox',
      '#title' => $this->t('Open AI queries'),
      '#default_value' => $user['open_ai_queries'] ?? FALSE,
      '#description' => $this->t('Lets this visitor ask their own questions of the AI on the FAQ page (when logged in). Off unless turned on here.'),
    ];
    $form['password'] = [
      '#type' => 'password_confirm',
      '#title' => $user === NULL ? $this->t('Password') : $this->t('New password'),
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
    ];
    return $form;
  }

  public function validateForm(array &$form, FormStateInterface $form_state): void {
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
    $profile = [
      'first_name' => trim((string) $form_state->getValue('first_name')),
      'last_name' => trim((string) $form_state->getValue('last_name')),
      'phone' => trim((string) $form_state->getValue('phone')),
    ];
    try {
      if ($userId === NULL) {
        $user = $this->manager->createSiteUser($email, $password, $emailVerified, $openAiQueries, $profile);
        $this->messenger()->addStatus($this->t('Added the account @email.', ['@email' => $user['email']]));
      }
      else {
        $user = $this->manager->updateSiteUser((int) $userId, $email, $password, $emailVerified, $openAiQueries, $profile);
        $this->messenger()->addStatus($password === ''
          ? $this->t('Saved @email.', ['@email' => $user['email']])
          : $this->t('Saved @email with the new password; it has been logged out everywhere.', ['@email' => $user['email']]));
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
