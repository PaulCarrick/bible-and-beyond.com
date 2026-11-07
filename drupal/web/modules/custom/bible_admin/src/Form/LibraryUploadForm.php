<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Form;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\bible_admin\Controller\LibraryListController;
use Drupal\Core\Form\FormBase;
use Drupal\Core\Form\FormStateInterface;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;
use Symfony\Component\HttpFoundation\File\UploadedFile;

/**
 * Step 1 of uploading a commentary or devotional: choose the file and describe it. The next page previews it.
 *
 * The file formats are described here and in ml-service/library_upload.py, which reads them.
 */
class LibraryUploadForm extends FormBase {

  private const ID_PATTERN = '/^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$/';

  public function __construct(protected BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_library_upload';
  }

  public function buildForm(array $form, FormStateInterface $form_state, string $collection = 'commentaries'): array {
    $form_state->set('collection', $collection);
    $isCommentary = $collection === 'commentaries';
    $isBook = $collection === 'books';
    $one = match ($collection) {
      'commentaries' => $this->t('commentary'),
      'books' => $this->t('book'),
      default => $this->t('devotional'),
    };
    $form['#title'] = $this->t('Upload a @one', ['@one' => $one]);

    $form['notice'] = [
      '#type' => 'html_tag',
      '#tag' => 'p',
      '#value' => $this->t('An uploaded @one is stored in the site\'s database and shown to the public once you publish it. Only upload text that is in the public domain or that you have permission to publish. Uploading again with the same id replaces its text.', ['@one' => $one]),
    ];
    $form['format'] = [
      '#type' => 'details',
      '#title' => $this->t('The file format'),
      '#open' => TRUE,
      'text' => [
        '#type' => 'inline_template',
        '#template' => $isCommentary
          ? '<p>{{ intro }}</p><pre>book&#9;chapter&#9;verse&#9;end_verse&#9;text
John&#9;3&#9;16&#9;&#9;God so loved the world ...
John&#9;3&#9;17&#9;21&#9;A note on verses 17 to 21.
John&#9;3&#9;22&#9;end&#9;A note to the end of the chapter.
John&#9;3&#9;&#9;&#9;An introduction to John 3.
John&#9;0&#9;&#9;&#9;An introduction to the book of John.</pre><p>{{ details }}</p>'
          : '<p>{{ intro }}</p><pre>section&#9;section_title&#9;unit&#9;unit_title&#9;heading&#9;text
1&#9;&#9;1&#9;&#9;Morning&#9;The morning reading of January 1 ...
1&#9;&#9;1&#9;&#9;Evening&#9;The evening reading of January 1 ...
1&#9;The First Book&#9;1&#9;Of the Imitation of Christ&#9;&#9;Chapter 1 (a devotional by chapter) ...</pre><p>{{ details }}</p>',
        '#context' => [
          'intro' => $this->t('Tab-separated text in UTF-8, with this header row and one row per @row (a spreadsheet can save it as "Tab-delimited text", UTF-8). In the text, \\n starts a new line; two of them start a new paragraph.', ['@row' => $isCommentary ? $this->t('note') : $this->t('reading')]),
          'details' => $isCommentary
            ? $this->t('The book is a number from 1 to 66, a code such as JHN or a name such as John or 1 Corinthians. end_verse is empty for the verse alone, a later verse for a range, or "end" for the rest of the chapter. Leave the verse empty for an introduction to the chapter; chapter 0 is the introduction to the book.')
            : ($isBook
              ? $this->t('The section is the part (a number, 0 for a preface) and the unit the chapter; both need their title on the first row of each. Several rows of one chapter are kept in their order.')
              : $this->t('Daily: the section is the month (1 to 12) and the unit the day; the titles may be left empty (they become "January" and "January 1"), and several rows for one day (a morning and an evening reading) keep their order and heading. By chapter: the section is the part or book (a number, 0 for a preface) and the unit the chapter; both need their title on the first row of each.')),
        ],
      ],
    ];

    $form['upload_file'] = [
      '#type' => 'file',
      '#title' => $this->t('The @one file', ['@one' => $one]),
      '#description' => $this->t('A .txt or .tsv file of up to @size MB.', ['@size' => (int) (BibleManager::MAX_UPLOAD_BYTES / 1048576)]),
    ];
    $form['id'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Id'),
      '#description' => $this->t('3 to 50 lowercase letters, digits and hyphens, such as @example. It names the @one in the site\'s addresses.', ['@example' => $isCommentary ? 'matthew-poole' : ($isBook ? 'mere-christianity' : 'my-utmost'), '@one' => $one]),
      '#required' => TRUE,
      '#maxlength' => 50,
      '#size' => 30,
    ];
    $form['name'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Name'),
      '#description' => $isCommentary ? $this->t('For example "Matthew Poole\'s Commentary".') : ($isBook ? $this->t('For example "The Cost of Discipleship".') : $this->t('For example "Streams in the Desert".')),
      '#required' => TRUE,
      '#maxlength' => 200,
    ];
    if ($isCommentary) {
      $form['short_name'] = [
        '#type' => 'textfield',
        '#title' => $this->t('Short name'),
        '#description' => $this->t('Up to 40 characters, used on the tabs and in search results, for example "Matthew Poole".'),
        '#required' => TRUE,
        '#maxlength' => 40,
        '#size' => 30,
      ];
    }
    else {
      $form['author'] = [
        '#type' => 'textfield',
        '#title' => $this->t('Author'),
        '#required' => TRUE,
        '#maxlength' => 200,
      ];
      $form['devotional_kind'] = $isBook ? ['#type' => 'value', '#value' => 'chapters'] : [
        '#type' => 'radios',
        '#title' => $this->t('Kind'),
        '#options' => [
          'daily' => $this->t('Daily: a reading for each day of the year (it opens at today\'s date)'),
          'chapters' => $this->t('By chapter: parts and chapters, read in order'),
        ],
        '#default_value' => 'daily',
        '#required' => TRUE,
      ];
      $form['translator'] = [
        '#type' => 'textfield',
        '#title' => $this->t('Translator'),
        '#description' => $this->t('Optional.'),
        '#maxlength' => 200,
      ];
    }
    $form['source_name'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Where the text came from'),
      '#description' => $this->t('Shown in the credit on the site, for example "Christian Classics Ethereal Library".'),
      '#required' => TRUE,
      '#maxlength' => 200,
    ];
    $form['source_url'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Its web address'),
      '#description' => $this->t('Starting with https://. Optional.'),
      '#maxlength' => 500,
    ];
    if ($isCommentary) {
      $form['license_url'] = [
        '#type' => 'textfield',
        '#title' => $this->t('Licence web address'),
        '#description' => $this->t('Leave empty for the Public Domain Mark (https://creativecommons.org/publicdomain/mark/1.0/).'),
        '#maxlength' => 500,
      ];
    }

    $form['actions'] = ['#type' => 'actions'];
    $form['actions']['submit'] = ['#type' => 'submit', '#value' => $this->t('Upload and preview')];
    $form['actions']['cancel'] = [
      '#type' => 'link',
      '#title' => $this->t('Cancel'),
      '#url' => Url::fromRoute('bible_admin.library', ['collection' => $collection]),
    ];
    return $form;
  }

  public function validateForm(array &$form, FormStateInterface $form_state): void {
    $file = $this->uploadedFile();
    if ($file === NULL) {
      $form_state->setErrorByName('upload_file', $this->t('Choose a file to upload.'));
    }
    elseif (!$file->isValid()) {
      $form_state->setErrorByName('upload_file', $this->t('The file could not be uploaded: @reason', ['@reason' => $file->getErrorMessage()]));
    }
    elseif (!in_array(strtolower($file->getClientOriginalExtension()), ['txt', 'tsv'], TRUE)) {
      $form_state->setErrorByName('upload_file', $this->t('The file must be a .txt or .tsv file.'));
    }
    elseif ($file->getSize() === 0) {
      $form_state->setErrorByName('upload_file', $this->t('The file is empty.'));
    }
    elseif ($file->getSize() > BibleManager::MAX_UPLOAD_BYTES) {
      $form_state->setErrorByName('upload_file', $this->t('The file is too large.'));
    }
    if (!preg_match(self::ID_PATTERN, strtolower(trim((string) $form_state->getValue('id'))))) {
      $form_state->setErrorByName('id', $this->t('The id must be 3 to 50 lowercase letters, digits and hyphens.'));
    }
    foreach (['source_url', 'license_url'] as $key) {
      $address = trim((string) $form_state->getValue($key));
      if ($address !== '' && !preg_match('#^https?://\S+$#', $address)) {
        $form_state->setErrorByName($key, $this->t('The address must start with http:// or https://.'));
      }
    }
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    $collection = (string) $form_state->get('collection');
    $parameters = ['collection' => $collection, 'kind' => LibraryListController::COLLECTIONS[$collection]['kind']];
    foreach (['id', 'name', 'short_name', 'author', 'devotional_kind', 'translator', 'source_name', 'source_url', 'license_url'] as $key) {
      $parameters[$key] = trim((string) $form_state->getValue($key));
    }
    $parameters['id'] = strtolower($parameters['id']);
    $token = NULL;
    try {
      $token = $this->manager->storeUpload($this->uploadedFile(), $parameters);
      $upload = $this->manager->loadUpload($token);
      $this->manager->savePreview($token, $this->manager->previewLibrary($upload['path'], $parameters));
    }
    catch (BibleManagerException $exception) {
      if ($token !== NULL) {
        $this->manager->removeUpload($token);
      }
      $this->messenger()->addError($exception->getMessage());
      $form_state->setRebuild();
      return;
    }
    $form_state->setRedirect('bible_admin.library_preview', ['collection' => $collection, 'token' => $token]);
  }

  private function uploadedFile(): ?UploadedFile {
    $files = $this->getRequest()->files->get('files');
    $file = is_array($files) ? ($files['upload_file'] ?? NULL) : NULL;
    return $file instanceof UploadedFile ? $file : NULL;
  }

}
