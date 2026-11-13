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
1&#9;The First Book&#9;1&#9;Of the Imitation of Christ&#9;&#9;Chapter 1 (a devotional by chapter) ...</pre><p>{{ details }}</p>{% if plain %}<p>{{ plain }}</p><pre>The Apostles’ Creed
I believe in God, the Father Almighty, creator of heaven and earth.
I believe in Jesus Christ, his only Son, our Lord ...</pre>{% endif %}<p>{{ links }}</p><pre>{{ link_example }}</pre>',
        '#context' => [
          'intro' => $this->t('Tab-separated text in UTF-8, with this header row and one row per @row (a spreadsheet can save it as "Tab-delimited text", UTF-8). In the text, \\n starts a new line; two of them start a new paragraph.', ['@row' => $isCommentary ? $this->t('note') : $this->t('reading')]),
          'details' => $isCommentary
            ? $this->t('The book is a number from 1 to 66, a code such as JHN or a name such as John or 1 Corinthians. end_verse is empty for the verse alone, a later verse for a range, or "end" for the rest of the chapter. Leave the verse empty for an introduction to the chapter; chapter 0 is the introduction to the book.')
            : ($isBook
              ? $this->t('The section is the part (a number, 0 for a preface) and the unit the chapter; both need their title on the first row of each. Several rows of one chapter are kept in their order.')
              : $this->t('Daily: the section is the month (1 to 12) and the unit the day; the titles may be left empty (they become "January" and "January 1"), and several rows for one day (a morning and an evening reading) keep their order and heading. By chapter: the section is the part or book (a number, 0 for a preface) and the unit the chapter; both need their title on the first row of each.')),
          'plain' => $isCommentary ? '' : $this->t('A short text of one chapter (a creed, a prayer, a short essay) can instead be plain text, with no tabs and no header row: the first line is its title, and each further line is a paragraph. Write it in any text editor and save it as UTF-8 text (.txt).') . ($isBook ? '' : ' ' . $this->t('Not for a daily devotional.')),
          'links' => $this->t('In any of these, words can be a link to the Bible verse they come from, without the reference showing: put them in double braces with the verse after a bar. On the site they read as ordinary text; a click opens the verse. The preview warns about a verse it cannot find.'),
          'link_example' => '{{who was conceived by the Holy Spirit|Luke 1:35}} {{and born of the Virgin Mary.|Matthew 1:23}}',
        ],
      ],
    ];

    $form['documents'] = [
      '#type' => 'details',
      '#title' => $this->t('A PDF, Word document or ebook'),
      '#open' => TRUE,
      'text' => [
        '#type' => 'html_tag',
        '#tag' => 'div',
        '#value' => '<p>' . $this->t('A PDF (.pdf), Word document (.docx) or EPUB ebook (.epub) can be uploaded as it is. Its formatting is kept: headings, bold, italic, underline, lists, quotations, superscript, tables, pictures and footnotes (not its fonts, colours or page layout). A scanned PDF (pictures of pages) is read by text recognition; check its text in the preview, as recognition can make mistakes. An ebook\'s table of contents says where its parts and chapters start. A Kindle book must first be converted to EPUB with the free Calibre app, and only an unlocked one can be used (not one bought from Amazon).') . '</p><p>'
          . ($isCommentary
            ? $this->t('It is cut into notes by its headings: a heading naming a book ("John"), a chapter ("John 3" or "Chapter 3") or verses ("John 3:16", "3:16-18", "Verse 16", "Verses 16–18"). The text under a chapter heading, before its first verse, is the chapter\'s introduction; under a book heading, the book\'s. Other headings stay inside the note. A document without such headings is one note on the passage typed below.')
            : ($isBook
              ? $this->t('It is cut into chapters by its headings (Heading 1, Heading 2 in Word; the bookmarks or the larger headings in a PDF): with two levels, the first starts a part and the second a chapter; with one level, each heading starts a chapter; with none, the whole document is one chapter, named after the book. A short title page before the first heading is left out.')
              : $this->t('Daily: each day starts with a heading that is a date, such as "January 1" or "1 January", and a day with two readings has headings "Morning" and "Evening" (or "January 1, Morning"). By chapter: cut by its headings as for Other books (two levels: parts and chapters; one: chapters; none: one chapter).')))
          . '</p>',
      ],
    ];
    $form['upload_file'] = [
      '#type' => 'file',
      '#title' => $this->t('The @one file', ['@one' => $one]),
      '#description' => $this->t('A .txt or .tsv file of up to @size MB, or a PDF (.pdf), Word document (.docx) or EPUB ebook (.epub) of up to @document MB.', [
        '@size' => (int) (BibleManager::MAX_UPLOAD_BYTES / 1048576),
        '@document' => (int) (BibleManager::MAX_DOCUMENT_BYTES / 1048576),
      ]),
      '#attributes' => ['accept' => '.txt,.tsv,.pdf,.docx,.epub'],
    ];
    if (!$isCommentary) {
      $form['whole'] = [
        '#type' => 'checkbox',
        '#title' => $this->t('Keep a PDF or Word document as one chapter'),
        '#description' => $isBook
          ? $this->t('The whole document becomes one chapter named after the book, with its headings inside it and nothing left out as a title page, instead of being cut into chapters at its headings. For a short text such as a lesson or a bulletin insert.')
          : $this->t('For a devotional by chapter: the whole document becomes one chapter named after the devotional, with its headings inside it, instead of being cut at its headings. A daily devotional is always read by its dates.'),
      ];
    }
    if ($isCommentary) {
      $form['passage'] = [
        '#type' => 'textfield',
        '#title' => $this->t('Passage (for a document without passage headings)'),
        '#description' => $this->t('Only for a PDF or Word document that is one note with no headings naming a passage: the verses it is about, such as John 3:16-21.'),
        '#maxlength' => 60,
      ];
    }
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
      $form['credit'] = [
        '#type' => 'textarea',
        '#title' => $this->t('Credit line'),
        '#description' => $this->t('Only for a text that is not in the public domain (a modern wording, or one used with permission): what to say about it under the text and on the copyright page, for example "This is a modern English wording of the Apostles’ Creed." Leave it empty for the usual line, "… by the author is in the public domain. The text comes from …". Uploading again replaces it.'),
        '#rows' => 2,
        '#maxlength' => 500,
      ];
      $form['keywords'] = [
        '#type' => 'textfield',
        '#title' => $this->t('Keywords'),
        '#description' => $this->t('Words or phrases, separated by commas, that a visitor might search for and that are not in the text itself, for example "recovery, addiction, step 4". The search pages find it by them. Optional; left empty, uploading again keeps the ones it has (change them on its Edit page).'),
        '#maxlength' => 500,
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
    // A link drawn as a button (the admin theme's "button" class), so it sits beside the other button.
    $form['actions']['cancel'] = [
      '#type' => 'link',
      '#title' => $this->t('Cancel'),
      '#url' => Url::fromRoute('bible_admin.library', ['collection' => $collection]),
      '#attributes' => ['class' => ['button']],
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
    elseif (in_array(strtolower($file->getClientOriginalExtension()), ['mobi', 'azw', 'azw3', 'kfx', 'prc'], TRUE)) {
      $form_state->setErrorByName('upload_file', $this->t('Kindle files (.mobi, .azw, .azw3, .kfx) cannot be read here. If the book is not locked (one you made or a free one), convert it to EPUB with the free Calibre app and upload the .epub. Books bought from Amazon are locked and cannot be used.'));
    }
    elseif (!in_array(strtolower($file->getClientOriginalExtension()), ['txt', 'tsv', 'pdf', 'docx', 'epub'], TRUE)) {
      $form_state->setErrorByName('upload_file', $this->t('The file must be a .txt or .tsv file, a PDF (.pdf), a Word document (.docx) or an EPUB ebook (.epub). An old .doc file must be saved again as .docx.'));
    }
    elseif ($file->getSize() === 0) {
      $form_state->setErrorByName('upload_file', $this->t('The file is empty.'));
    }
    elseif ($file->getSize() > (in_array(strtolower($file->getClientOriginalExtension()), ['pdf', 'docx', 'epub'], TRUE) ? BibleManager::MAX_DOCUMENT_BYTES : BibleManager::MAX_UPLOAD_BYTES)) {
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
    foreach (['id', 'name', 'short_name', 'author', 'devotional_kind', 'translator', 'source_name', 'source_url', 'license_url', 'credit', 'keywords', 'passage'] as $key) {
      $parameters[$key] = trim((string) $form_state->getValue($key));
    }
    $parameters['whole'] = (bool) $form_state->getValue('whole');
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
