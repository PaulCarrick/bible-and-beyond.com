<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Form;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\bible_admin\MailSettings;
use Drupal\Component\Utility\EmailValidatorInterface;
use Drupal\Core\Config\ConfigFactoryInterface;
use Drupal\Core\Form\FormBase;
use Drupal\Core\Form\FormStateInterface;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * The one screen where the options of the public site are set.
 *
 * What a person sees and can change depends on who they are. Someone who may administer Bibles sees
 * the two numbers for the verse windows. Someone who may administer the site also sees the site
 * title, the copyright line and the email server settings.
 *
 * The title, the copyright line and the numbers are saved in the Bible database, which the public
 * site reads, so a change shows at once. The email settings, which include a password, are saved in
 * Drupal and never reach the public site.
 */
class SiteSettingsForm extends FormBase {

  private const NUMBER_FIELDS = [
    'context_verses_before' => 'Verses before',
    'context_verses_after' => 'Verses after',
    'related_verses_limit' => 'Related verses to show',
  ];

  private const HOST_PATTERN = '/^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$/';

  public function __construct(
    private readonly BibleManager $manager,
    private readonly ConfigFactoryInterface $mailConfigFactory,
    private readonly EmailValidatorInterface $emailValidator,
  ) {}

  public static function create(ContainerInterface $container): static {
    return new static(
      $container->get('bible_admin.manager'),
      $container->get('config.factory'),
      $container->get('email.validator'),
    );
  }

  public function getFormId(): string {
    return 'bible_admin_site_settings';
  }

  /**
   * Whether this person may change the title, the copyright line and the email settings.
   */
  private function canEditSite(): bool {
    return $this->currentUser()->hasPermission('administer site configuration');
  }

  /**
   * Whether this person may change the numbers for the verse windows.
   */
  private function canEditSearch(): bool {
    return $this->currentUser()->hasPermission('administer bibles');
  }

  public function buildForm(array $form, FormStateInterface $form_state): array {
    try {
      $current = $this->manager->getSiteSettings();
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return $form;
    }
    $settings = $current['settings'];
    $limits = $current['limits'];
    $textLimits = $current['text_limits'];
    $form_state->set('limits', $limits);
    $form_state->set('text_limits', $textLimits);

    $form['intro'] = [
      '#type' => 'html_tag',
      '#tag' => 'p',
      '#value' => $this->t('The options for the public site, on one screen. Changes to the site title, the copyright line and the numbers show on the public site straight away.'),
    ];

    if ($this->canEditSite()) {
      $form['site'] = [
        '#type' => 'details',
        '#title' => $this->t('The site'),
        '#open' => TRUE,
      ];
      $form['site']['site_title'] = [
        '#type' => 'textfield',
        '#title' => $this->t('Title'),
        '#description' => $this->t('The name at the top of every page, next to the icon, and the title of the browser tab. Up to @max characters.', ['@max' => $textLimits['site_title']['max']]),
        '#default_value' => $settings['site_title'],
        '#maxlength' => $textLimits['site_title']['max'],
        '#required' => TRUE,
      ];
      $form['site']['copyright_text'] = [
        '#type' => 'textfield',
        '#title' => $this->t('Copyright'),
        '#description' => $this->t('The site\'s own copyright line in the footer, shown under the notices for the licensed Bibles and the other credits. Plain text on one line, up to @max characters. Leave it empty to show none.', ['@max' => $textLimits['copyright_text']['max']]),
        '#default_value' => $settings['copyright_text'],
        '#maxlength' => $textLimits['copyright_text']['max'],
        '#size' => 80,
      ];
    }

    if ($this->canEditSearch()) {
      $form['context'] = [
        '#type' => 'details',
        '#title' => $this->t('Show in Context'),
        '#description' => $this->t('Shows the verse in the middle with this many verses around it, in reading order. The window stops at the start and end of the book.'),
        '#open' => TRUE,
      ];
      $form['related'] = [
        '#type' => 'details',
        '#title' => $this->t('Related Verses'),
        '#description' => $this->t('Lists the verses that readers have cross-referenced with the chosen verse, best-voted first. Showing more is slower to read.'),
        '#open' => TRUE,
      ];
      foreach (self::NUMBER_FIELDS as $key => $label) {
        $group = $key === 'related_verses_limit' ? 'related' : 'context';
        $form[$group][$key] = [
          '#type' => 'number',
          '#title' => $this->t($label),
          '#description' => $this->t('From @min to @max.', ['@min' => $limits[$key]['min'], '@max' => $limits[$key]['max']]),
          '#default_value' => $settings[$key],
          '#min' => $limits[$key]['min'],
          '#max' => $limits[$key]['max'],
          '#step' => 1,
          '#required' => TRUE,
        ];
      }
    }

    if ($this->canEditSite()) {
      $mail = MailSettings::load($this->mailConfigFactory);
      $form['mail'] = [
        '#type' => 'details',
        '#title' => $this->t('Email server'),
        '#description' => $this->t('For the contact form. Nothing sends email with these yet; they are saved here for when there is a contact form. They are kept in this Drupal site only and are never shown on the public site.'),
        '#open' => TRUE,
      ];
      $form['mail']['smtp_host'] = [
        '#type' => 'textfield',
        '#title' => $this->t('Email server (SMTP host)'),
        '#default_value' => $mail['smtp_host'],
        '#maxlength' => 253,
        '#required' => TRUE,
      ];
      $form['mail']['smtp_port'] = [
        '#type' => 'number',
        '#title' => $this->t('Email server port'),
        '#description' => $this->t('Usually 587.'),
        '#default_value' => $mail['smtp_port'],
        '#min' => 1,
        '#max' => 65535,
        '#step' => 1,
        '#required' => TRUE,
      ];
      $form['mail']['smtp_username'] = [
        '#type' => 'textfield',
        '#title' => $this->t('Email server user name'),
        '#default_value' => $mail['smtp_username'],
        '#maxlength' => 255,
        '#attributes' => ['autocomplete' => 'off'],
      ];
      $hasPassword = $mail['smtp_password'] !== '';
      $form['mail']['smtp_password'] = [
        '#type' => 'password',
        '#title' => $this->t('Email server password'),
        '#description' => $hasPassword
          ? $this->t('A password is saved. Leave this empty to keep it, or type a new one to replace it.')
          : $this->t('No password is saved yet.'),
        '#maxlength' => 255,
        '#attributes' => ['autocomplete' => 'new-password'],
      ];
      if ($hasPassword) {
        $form['mail']['smtp_password_remove'] = [
          '#type' => 'checkbox',
          '#title' => $this->t('Remove the saved password'),
        ];
      }
      $form['mail']['smtp_authentication'] = [
        '#type' => 'select',
        '#title' => $this->t('Email server authentication'),
        '#options' => MailSettings::AUTHENTICATIONS,
        '#default_value' => $mail['smtp_authentication'],
        '#required' => TRUE,
      ];
      $form['mail']['default_domain'] = [
        '#type' => 'textfield',
        '#title' => $this->t('Email server default domain'),
        '#default_value' => $mail['default_domain'],
        '#maxlength' => 253,
      ];
      $form['mail']['from_address'] = [
        '#type' => 'email',
        '#title' => $this->t('Contact "Email From:"'),
        '#default_value' => $mail['from_address'],
        '#maxlength' => 254,
        '#required' => TRUE,
      ];
      $form['mail']['to_address'] = [
        '#type' => 'email',
        '#title' => $this->t('Contact email to'),
        '#default_value' => $mail['to_address'],
        '#maxlength' => 254,
        '#required' => TRUE,
      ];
      $form['mail']['subject'] = [
        '#type' => 'textfield',
        '#title' => $this->t('Contact email subject'),
        '#default_value' => $mail['subject'],
        '#maxlength' => 200,
        '#required' => TRUE,
      ];
    }

    $form['actions'] = ['#type' => 'actions'];
    $form['actions']['submit'] = [
      '#type' => 'submit',
      '#value' => $this->t('Save'),
      '#button_type' => 'primary',
    ];
    return $form;
  }

  public function validateForm(array &$form, FormStateInterface $form_state): void {
    if ($this->canEditSearch()) {
      $limits = $form_state->get('limits');
      foreach (self::NUMBER_FIELDS as $key => $label) {
        $value = $form_state->getValue($key);
        $min = (int) $limits[$key]['min'];
        $max = (int) $limits[$key]['max'];
        if (!is_numeric($value) || (string) (int) $value !== trim((string) $value) || (int) $value < $min || (int) $value > $max) {
          $form_state->setErrorByName($key, $this->t('@label must be a whole number from @min to @max.', ['@label' => $label, '@min' => $min, '@max' => $max]));
        }
      }
    }

    if (!$this->canEditSite()) {
      return;
    }
    $textLimits = $form_state->get('text_limits');
    $title = trim((string) $form_state->getValue('site_title'));
    if ($title === '' || mb_strlen($title) > (int) $textLimits['site_title']['max']) {
      $form_state->setErrorByName('site_title', $this->t('The title must be from 1 to @max characters.', ['@max' => $textLimits['site_title']['max']]));
    }
    elseif ($this->hasControlCharacters($title)) {
      $form_state->setErrorByName('site_title', $this->t('The title must be one line of plain text.'));
    }
    $copyright = trim((string) $form_state->getValue('copyright_text'));
    if (mb_strlen($copyright) > (int) $textLimits['copyright_text']['max']) {
      $form_state->setErrorByName('copyright_text', $this->t('The copyright line can be at most @max characters.', ['@max' => $textLimits['copyright_text']['max']]));
    }
    elseif ($this->hasControlCharacters($copyright)) {
      $form_state->setErrorByName('copyright_text', $this->t('The copyright line must be one line of plain text.'));
    }

    $host = trim((string) $form_state->getValue('smtp_host'));
    if (!preg_match(self::HOST_PATTERN, $host)) {
      $form_state->setErrorByName('smtp_host', $this->t('The email server must be a host name such as mail.example.com.'));
    }
    $port = $form_state->getValue('smtp_port');
    if (!is_numeric($port) || (string) (int) $port !== trim((string) $port) || (int) $port < 1 || (int) $port > 65535) {
      $form_state->setErrorByName('smtp_port', $this->t('The email server port must be a whole number from 1 to 65535.'));
    }
    $domain = trim((string) $form_state->getValue('default_domain'));
    if ($domain !== '' && !preg_match(self::HOST_PATTERN, $domain)) {
      $form_state->setErrorByName('default_domain', $this->t('The default domain must be a domain name such as example.com, or empty.'));
    }
    if (!array_key_exists((string) $form_state->getValue('smtp_authentication'), MailSettings::AUTHENTICATIONS)) {
      $form_state->setErrorByName('smtp_authentication', $this->t('Choose one of the ways to sign in that are listed.'));
    }
    foreach (['from_address' => $this->t('Contact "Email From:"'), 'to_address' => $this->t('Contact email to')] as $key => $label) {
      if (!$this->emailValidator->isValid(trim((string) $form_state->getValue($key)))) {
        $form_state->setErrorByName($key, $this->t('@label must be an email address.', ['@label' => $label]));
      }
    }
    $subject = trim((string) $form_state->getValue('subject'));
    if ($subject === '' || $this->hasControlCharacters($subject)) {
      $form_state->setErrorByName('subject', $this->t('The subject must be one line of text.'));
    }
    foreach (['smtp_username' => $this->t('The user name'), 'smtp_password' => $this->t('The password')] as $key => $label) {
      if ($this->hasControlCharacters((string) $form_state->getValue($key))) {
        $form_state->setErrorByName($key, $this->t('@label must be one line of text.', ['@label' => $label]));
      }
    }
  }

  private function hasControlCharacters(string $text): bool {
    return (bool) preg_match('/[\x00-\x1f\x7f]/', $text);
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    $values = [];
    if ($this->canEditSearch()) {
      foreach (array_keys(self::NUMBER_FIELDS) as $key) {
        $values[$key] = (int) $form_state->getValue($key);
      }
    }
    if ($this->canEditSite()) {
      $values['site_title'] = trim((string) $form_state->getValue('site_title'));
      $values['copyright_text'] = trim((string) $form_state->getValue('copyright_text'));
    }

    try {
      $this->manager->saveSiteSettings($values);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      $form_state->setRebuild();
      return;
    }

    if ($this->canEditSite()) {
      $mail = [];
      foreach (['smtp_host', 'smtp_username', 'smtp_authentication', 'default_domain', 'from_address', 'to_address', 'subject'] as $key) {
        $mail[$key] = trim((string) $form_state->getValue($key));
      }
      $mail['smtp_port'] = (int) $form_state->getValue('smtp_port');
      $password = (string) $form_state->getValue('smtp_password');
      MailSettings::save(
        $this->mailConfigFactory,
        $mail,
        $password === '' ? NULL : $password,
        (bool) $form_state->getValue('smtp_password_remove'),
      );
      // The password is never written to the log.
      $this->getLogger('bible_admin')->notice('@user changed the email server settings.', ['@user' => $this->currentUser()->getAccountName()]);
    }

    $this->messenger()->addStatus($this->t('Saved. The public site uses the new settings now.'));
  }

}
