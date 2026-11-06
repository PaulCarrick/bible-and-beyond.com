<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Form;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\Core\Form\FormBase;
use Drupal\Core\Form\FormStateInterface;
use Symfony\Component\DependencyInjection\ContainerInterface;
use Symfony\Component\HttpFoundation\File\UploadedFile;

/**
 * Step 1: choose a Bible text file and describe it. The next page previews it.
 */
class UploadForm extends FormBase {

  public function __construct(private readonly BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_upload';
  }

  public function buildForm(array $form, FormStateInterface $form_state): array {
    $form['notice'] = [
      '#type' => 'html_tag',
      '#tag' => 'p',
      '#value' => $this->t('The text of an uploaded Bible is stored in the search database and shown to the public once you publish it. Only upload text that is in the public domain or that you have permission to publish.'),
    ];

    $form['bible_file'] = [
      '#type' => 'file',
      '#title' => $this->t('Bible text file'),
      '#description' => $this->t('A UTF-8 text file (.txt) of up to @size MB, with one verse per line.', ['@size' => (int) (BibleManager::MAX_UPLOAD_BYTES / 1048576)]),
    ];
    $form['code'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Code'),
      '#description' => $this->t('A short code of 2 to 10 letters or digits, such as NASB95. It is how the translation is named in the search page. Using the code of an existing Bible replaces that Bible.'),
      '#required' => TRUE,
      '#maxlength' => 10,
      '#size' => 12,
    ];
    $form['name'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Name'),
      '#description' => $this->t('For example "American Standard Version".'),
      '#required' => TRUE,
      '#maxlength' => 100,
    ];
    $form['language'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Language'),
      '#description' => $this->t('A language code such as en or es.'),
      '#default_value' => 'en',
      '#required' => TRUE,
      '#maxlength' => 12,
      '#size' => 8,
    ];
    $form['license'] = [
      '#type' => 'textfield',
      '#title' => $this->t('License'),
      '#description' => $this->t('For example "Public domain". Required.'),
      '#required' => TRUE,
      '#maxlength' => 300,
    ];
    $form['source_url'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Where the text came from'),
      '#description' => $this->t('A web address starting with https://. Optional.'),
      '#maxlength' => 500,
    ];

    $formats = ['auto' => $this->t('Detect it from the file (recommended)')];
    try {
      foreach ($this->manager->listFormats() as $format) {
        $formats[$format['id']] = $format['name'] . ' — ' . $format['description'];
      }
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
    }
    $form['format'] = [
      '#type' => 'select',
      '#title' => $this->t('File format'),
      '#options' => $formats,
      '#default_value' => 'auto',
    ];
    $form['strip_brackets'] = [
      '#type' => 'checkbox',
      '#title' => $this->t('Remove [ and ] around words'),
      '#description' => $this->t('Some Bibles, such as the King James Version, mark supplied words with square brackets.'),
    ];
    $form['skip_unmatched_books'] = [
      '#type' => 'checkbox',
      '#title' => $this->t('Skip books I do not recognize'),
      '#description' => $this->t('For example the Apocrypha. Without this, an unknown book stops the import.'),
    ];

    $form['actions'] = ['#type' => 'actions'];
    $form['actions']['submit'] = [
      '#type' => 'submit',
      '#value' => $this->t('Upload and preview'),
    ];
    return $form;
  }

  public function validateForm(array &$form, FormStateInterface $form_state): void {
    $file = $this->uploadedFile();
    if ($file === NULL) {
      $form_state->setErrorByName('bible_file', $this->t('Choose a Bible text file to upload.'));
    }
    elseif (!$file->isValid()) {
      $form_state->setErrorByName('bible_file', $this->t('The file could not be uploaded: @reason', ['@reason' => $file->getErrorMessage()]));
    }
    elseif (strtolower($file->getClientOriginalExtension()) !== 'txt') {
      $form_state->setErrorByName('bible_file', $this->t('The file must be a .txt file.'));
    }
    elseif ($file->getSize() === 0) {
      $form_state->setErrorByName('bible_file', $this->t('The file is empty.'));
    }
    elseif ($file->getSize() > BibleManager::MAX_UPLOAD_BYTES) {
      $form_state->setErrorByName('bible_file', $this->t('The file is too large.'));
    }

    $code = strtoupper(trim((string) $form_state->getValue('code')));
    if (!preg_match('/^[A-Z0-9]{2,10}$/', $code)) {
      $form_state->setErrorByName('code', $this->t('The code must be 2 to 10 letters or digits.'));
    }
    if (!preg_match('/^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$/', trim((string) $form_state->getValue('language')))) {
      $form_state->setErrorByName('language', $this->t('The language must be a language code such as en or es.'));
    }
    $sourceUrl = trim((string) $form_state->getValue('source_url'));
    if ($sourceUrl !== '' && !preg_match('#^https?://\S+$#', $sourceUrl)) {
      $form_state->setErrorByName('source_url', $this->t('The address must start with http:// or https://.'));
    }
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    $parameters = [
      'code' => strtoupper(trim((string) $form_state->getValue('code'))),
      'name' => trim((string) $form_state->getValue('name')),
      'language' => trim((string) $form_state->getValue('language')),
      'license' => trim((string) $form_state->getValue('license')),
      'source_url' => trim((string) $form_state->getValue('source_url')),
      'format' => (string) $form_state->getValue('format'),
      'strip_brackets' => (bool) $form_state->getValue('strip_brackets'),
      'skip_unmatched_books' => (bool) $form_state->getValue('skip_unmatched_books'),
    ];

    $token = NULL;
    try {
      $token = $this->manager->storeUpload($this->uploadedFile(), $parameters);
      $upload = $this->manager->loadUpload($token);
      $this->manager->savePreview($token, $this->manager->preview($upload['path'], $parameters));
    }
    catch (BibleManagerException $exception) {
      if ($token !== NULL) {
        $this->manager->removeUpload($token);
      }
      $this->messenger()->addError($exception->getMessage());
      $form_state->setRebuild();
      return;
    }
    $form_state->setRedirect('bible_admin.preview', ['token' => $token]);
  }

  private function uploadedFile(): ?UploadedFile {
    $files = $this->getRequest()->files->get('files');
    $file = is_array($files) ? ($files['bible_file'] ?? NULL) : NULL;
    return $file instanceof UploadedFile ? $file : NULL;
  }

}
