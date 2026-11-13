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
use Symfony\Component\HttpFoundation\File\UploadedFile;

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

  /**
   * The two icons that can be uploaded: field name prefix => what it is.
   */
  private const ICONS = [
    'header' => 'Header emblem',
    'tab' => 'Browser-tab icon',
  ];

  private const HOST_PATTERN = '/^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$/';

  /**
   * The keys of the outside services: hidden fields that are never filled in from what is saved.
   */
  private const SERVICE_KEYS = ['gemini_api_key', 'api_bible_key', 'recaptcha_secret_key'];

  /**
   * The other service options, shown and saved as they are.
   */
  private const SERVICE_OPTIONS = ['gemini_models', 'api_bible_endpoint', 'api_bible_monthly_limit', 'recaptcha_site_key', 'recaptcha_minimum_score', 'music_folder'];

  public function __construct(
    protected BibleManager $manager,
    protected ConfigFactoryInterface $mailConfigFactory,
    protected EmailValidatorInterface $emailValidator,
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
    // The module's own permission (the Website administrator role), or Drupal's (the administrator).
    return $this->currentUser()->hasPermission('administer site settings')
      || $this->currentUser()->hasPermission('administer site configuration');
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
      $this->buildIcons($form);
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
        '#description' => $this->t('For the contact form and the emails the site sends (account links and the daily devotionals). They are kept in this Drupal site only and are never shown on the public site.'),
        '#open' => TRUE,
      ];
      $form['mail']['smtp_host'] = [
        '#type' => 'textfield',
        '#title' => $this->t('Email server (SMTP host)'),
        '#description' => $this->t('Leave this and the two contact addresses empty if this site sends no email (a local copy, say); the site then sends none.'),
        '#default_value' => $mail['smtp_host'],
        '#maxlength' => 253,
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
      ];
      $form['mail']['to_address'] = [
        '#type' => 'email',
        '#title' => $this->t('Contact email to'),
        '#default_value' => $mail['to_address'],
        '#maxlength' => 254,
      ];
      $form['mail']['subject'] = [
        '#type' => 'textfield',
        '#title' => $this->t('Contact email subject'),
        '#default_value' => $mail['subject'],
        '#maxlength' => 200,
        '#required' => TRUE,
      ];
    }

    if ($this->canEditSite()) {
      $this->buildServiceSettings($form, $form_state);
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
    foreach (self::ICONS as $kind => $label) {
      $file = $this->uploadedIcon($kind);
      if ($file === NULL) {
        continue;
      }
      if (!$file->isValid()) {
        $form_state->setErrorByName($kind . '_icon', $this->t('The @label could not be uploaded: @reason', ['@label' => mb_strtolower($label), '@reason' => $file->getErrorMessage()]));
      }
      elseif (!in_array(strtolower($file->getClientOriginalExtension()), BibleManager::ICON_EXTENSIONS, TRUE)) {
        $form_state->setErrorByName($kind . '_icon', $this->t('The @label must be a PNG, JPEG, WebP, GIF, ICO or SVG file.', ['@label' => mb_strtolower($label)]));
      }
      elseif ($file->getSize() > BibleManager::MAX_ICON_BYTES) {
        $form_state->setErrorByName($kind . '_icon', $this->t('The @label is larger than @size KB.', ['@label' => mb_strtolower($label), '@size' => (int) (BibleManager::MAX_ICON_BYTES / 1024)]));
      }
    }
    $copyright = trim((string) $form_state->getValue('copyright_text'));
    if (mb_strlen($copyright) > (int) $textLimits['copyright_text']['max']) {
      $form_state->setErrorByName('copyright_text', $this->t('The copyright line can be at most @max characters.', ['@max' => $textLimits['copyright_text']['max']]));
    }
    elseif ($this->hasControlCharacters($copyright)) {
      $form_state->setErrorByName('copyright_text', $this->t('The copyright line must be one line of plain text.'));
    }

    // The email server may be left empty (a site that sends no email); what is typed must be valid.
    $host = trim((string) $form_state->getValue('smtp_host'));
    if ($host !== '' && !preg_match(self::HOST_PATTERN, $host)) {
      $form_state->setErrorByName('smtp_host', $this->t('The email server must be a host name such as mail.example.com, or empty.'));
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
      $address = trim((string) $form_state->getValue($key));
      if ($address !== '' && !$this->emailValidator->isValid($address)) {
        $form_state->setErrorByName($key, $this->t('@label must be an email address, or empty.', ['@label' => $label]));
      }
    }
    $subject = trim((string) $form_state->getValue('subject'));
    if ($subject === '' || $this->hasControlCharacters($subject)) {
      $form_state->setErrorByName('subject', $this->t('The subject must be one line of text.'));
    }
    foreach ([...self::SERVICE_KEYS, ...self::SERVICE_OPTIONS] as $key) {
      if ($form_state->get('service_loaded') && $this->hasControlCharacters((string) $form_state->getValue($key))) {
        $form_state->setErrorByName($key, $this->t('Each key and option must be one line of text.'));
      }
    }
    foreach (['smtp_username' => $this->t('The user name'), 'smtp_password' => $this->t('The password')] as $key => $label) {
      if ($this->hasControlCharacters((string) $form_state->getValue($key))) {
        $form_state->setErrorByName($key, $this->t('@label must be one line of text.', ['@label' => $label]));
      }
    }
  }

  /**
   * The keys and options of Gemini, API.Bible and reCAPTCHA. They are kept in a private file on the server
   * (not in a database); until the first save the values in ml-service/.env are used.
   */
  private function buildServiceSettings(array &$form, FormStateInterface $form_state): void {
    try {
      $service = $this->manager->getServiceSettings();
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($this->t('The service keys could not be read: @message', ['@message' => $exception->getMessage()]));
      return;
    }
    $settings = $service['settings'];
    $form_state->set('service_loaded', TRUE);

    $form['services_intro'] = [
      '#type' => 'html_tag',
      '#tag' => 'p',
      '#value' => $service['is_saved']
        ? $this->t('The keys and options below are the ones the site uses. They are kept in a private file on the server, not in a database, so they are not in the database backups.')
        : $this->t('The keys and options below come from ml-service/.env for now. When you save this screen they are copied to a private file on the server (not a database), and from then on these fields are the ones the site uses.'),
    ];

    $sections = [
      'gemini' => [
        'title' => $this->t('Google Gemini (the AI answers on the FAQ page)'),
        'fields' => ['gemini_api_key', 'gemini_models'],
      ],
      'api_bible' => [
        'title' => $this->t('API.Bible (the NIV, NASB and The Message)'),
        'fields' => ['api_bible_key', 'api_bible_endpoint', 'api_bible_monthly_limit'],
      ],
      'recaptcha' => [
        'title' => $this->t('Google reCAPTCHA (the contact form)'),
        'fields' => ['recaptcha_site_key', 'recaptcha_secret_key', 'recaptcha_minimum_score'],
      ],
      'music' => [
        'title' => $this->t('Christian music (where the song files are kept)'),
        'fields' => ['music_folder'],
      ],
    ];
    $labels = [
      'gemini_api_key' => $this->t('Gemini API key'),
      'gemini_models' => $this->t('Gemini models'),
      'api_bible_key' => $this->t('API.Bible key'),
      'api_bible_endpoint' => $this->t('API.Bible address'),
      'api_bible_monthly_limit' => $this->t('API.Bible requests a month'),
      'recaptcha_site_key' => $this->t('reCAPTCHA site key'),
      'recaptcha_secret_key' => $this->t('reCAPTCHA secret key'),
      'recaptcha_minimum_score' => $this->t('reCAPTCHA minimum score'),
      'music_folder' => $this->t('Music folder'),
    ];
    $descriptions = [
      'gemini_models' => $this->t('Tried in order, separated by commas; the next is tried when one is busy. Leave empty for the default (gemini-3.6-flash, gemini-flash-latest).'),
      'api_bible_endpoint' => $this->t('Usually https://rest.api.bible.'),
      'api_bible_monthly_limit' => $this->t('The site stops asking API.Bible after this many requests in a month (the free plan allows 5,000).'),
      'recaptcha_site_key' => $this->t('The public key of a reCAPTCHA v3 key pair; the contact form shows it to visitors.'),
      'recaptcha_minimum_score' => $this->t('From 0 to 1. Messages scoring lower are refused as robots; 0.5 is usual.'),
      'music_folder' => $this->t('A full path on the server, such as /mnt/music. The MP3 and MP4 files uploaded on the Christian music page are kept here. To move them (for example to a bigger volume), copy the files to the new folder first, then change this; the files are not moved for you. The folder is made if it does not exist.'),
    ];

    foreach ($sections as $section => $definition) {
      $form[$section] = ['#type' => 'details', '#title' => $definition['title'], '#open' => TRUE];
      foreach ($definition['fields'] as $name) {
        $entry = $settings[$name];
        $fromEnvironment = $entry['source'] === 'env';
        if (in_array($name, self::SERVICE_KEYS, TRUE)) {
          $form[$section][$name] = [
            '#type' => 'password',
            '#title' => $labels[$name],
            '#description' => match (TRUE) {
              !$entry['is_set'] => $this->t('No key is set.'),
              $fromEnvironment => $this->t('The key in ml-service/.env (@variable) is in use. Leave this empty to keep it (saving copies it here), or type a new one.', ['@variable' => $entry['environment_variable']]),
              default => $this->t('A key is saved. Leave this empty to keep it, or type a new one to replace it.'),
            },
            '#maxlength' => 500,
            '#size' => 60,
            '#attributes' => ['autocomplete' => 'new-password'],
          ];
          if ($entry['is_set']) {
            $form[$section][$name . '_remove'] = [
              '#type' => 'checkbox',
              '#title' => $this->t('Remove this key (the service stops working on the site)'),
            ];
          }
          continue;
        }
        $description = $descriptions[$name] ?? '';
        if ($fromEnvironment) {
          $description = $this->t('@description (Now from ml-service/.env, @variable.)', ['@description' => $description, '@variable' => $entry['environment_variable']]);
        }
        $form[$section][$name] = match ($entry['kind']) {
          'count' => ['#type' => 'number', '#min' => 0, '#max' => (int) $service['count_limit'], '#step' => 1, '#required' => TRUE],
          'score' => ['#type' => 'number', '#min' => 0, '#max' => 1, '#step' => 0.05, '#required' => TRUE],
          'url' => ['#type' => 'url', '#maxlength' => 300, '#required' => TRUE],
          default => ['#type' => 'textfield', '#maxlength' => 500, '#size' => 60],
        } + [
          '#title' => $labels[$name],
          '#description' => $description,
          '#default_value' => $entry['value'],
        ];
      }
    }
  }

  /**
   * The two icons, in The site section: each with a preview of the one in use, an upload field and, when one
   * was uploaded, a box to go back to the site's own.
   */
  private function buildIcons(array &$form): void {
    try {
      $icons = $this->manager->getSiteIcons();
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($this->t('The icons could not be read: @message', ['@message' => $exception->getMessage()]));
      return;
    }
    $descriptions = [
      'header' => $this->t('The emblem at the top of every page, beside the title. It is shown 44 pixels square (38 on a phone), so a square picture of at least 88 by 88 pixels looks best. The site\'s own is the round navy emblem with the gold "&".'),
      'tab' => $this->t('The small picture on the browser tab (the favicon). A square picture, at least 32 by 32 pixels (64 or more for sharp screens). The site\'s own is the open book.'),
    ];
    foreach (self::ICONS as $kind => $label) {
      $icon = $icons[$kind] ?? NULL;
      $form['site'][$kind . '_icon_group'] = [
        '#type' => 'fieldset',
        '#title' => $this->t($label),
      ];
      $form['site'][$kind . '_icon_group']['current'] = [
        '#type' => 'html_tag',
        '#tag' => 'p',
        '#value' => $icon === NULL
          ? $this->t("The site's own icon is in use.")
          : $this->t('An uploaded icon is in use (@type, @size KB):', [
            '@type' => strtoupper(preg_replace('#^image/(x-)?|\+xml$#', '', $icon['media_type'])),
            '@size' => max(1, (int) round($icon['size'] / 1024)),
          ]),
      ];
      if ($icon !== NULL) {
        // A data: address made by the tool from the stored file; an SVG drawn by <img> cannot run anything.
        $form['site'][$kind . '_icon_group']['preview'] = [
          '#type' => 'html_tag',
          '#tag' => 'img',
          '#attributes' => [
            'src' => $icon['data_uri'],
            'alt' => $this->t('The @label in use', ['@label' => mb_strtolower($label)]),
            'width' => 64,
            'height' => 64,
            'style' => 'object-fit: contain; border: 1px solid #ccc; padding: 4px; background: #fff;',
          ],
        ];
      }
      $form['site'][$kind . '_icon_group'][$kind . '_icon'] = [
        '#type' => 'file',
        '#title' => $icon === NULL ? $this->t('Upload a new icon') : $this->t('Upload a different icon'),
        '#description' => $descriptions[$kind] . ' ' . $this->t('PNG, JPEG, WebP, GIF, ICO or SVG, up to @size KB. Leave empty to keep the one in use.', ['@size' => (int) (BibleManager::MAX_ICON_BYTES / 1024)]),
        '#attributes' => ['accept' => '.png,.jpg,.jpeg,.webp,.gif,.ico,.svg'],
      ];
      if ($icon !== NULL) {
        $form['site'][$kind . '_icon_group'][$kind . '_icon_remove'] = [
          '#type' => 'checkbox',
          '#title' => $this->t("Go back to the site's own icon"),
        ];
      }
    }
  }

  /**
   * The file uploaded in one of the icon fields, or NULL when none was chosen.
   */
  private function uploadedIcon(string $kind): ?UploadedFile {
    $files = $this->getRequest()->files->get('files');
    $file = is_array($files) ? ($files[$kind . '_icon'] ?? NULL) : NULL;
    return $file instanceof UploadedFile ? $file : NULL;
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
      // The icons: a new upload replaces the one in use; "Go back" removes an uploaded one.
      foreach (array_keys(self::ICONS) as $kind) {
        try {
          $file = $this->uploadedIcon($kind);
          if ($file !== NULL) {
            $this->manager->saveSiteIcon($kind, $file);
          }
          elseif ($form_state->getValue($kind . '_icon_remove')) {
            $this->manager->removeSiteIcon($kind);
          }
        }
        catch (BibleManagerException $exception) {
          $this->messenger()->addError($this->t('The @label was not changed: @message', ['@label' => mb_strtolower(self::ICONS[$kind]), '@message' => $exception->getMessage()]));
        }
      }

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

      // The service keys (only when they could be read, so a failure to read them cannot wipe them).
      if ($form_state->get('service_loaded')) {
        $values = [];
        foreach ([...self::SERVICE_OPTIONS, ...self::SERVICE_KEYS] as $key) {
          $values[$key] = trim((string) $form_state->getValue($key));
        }
        $remove = array_values(array_filter(self::SERVICE_KEYS, fn ($key) => (bool) $form_state->getValue($key . '_remove')));
        try {
          $this->manager->saveServiceSettings($values, $remove);
        }
        catch (BibleManagerException $exception) {
          $this->messenger()->addError($this->t('The other settings were saved, but not the service keys: @message', ['@message' => $exception->getMessage()]));
          $form_state->setRebuild();
          return;
        }
      }
    }

    $this->messenger()->addStatus($this->t('Saved. The public site uses the new settings now.'));
  }

}
