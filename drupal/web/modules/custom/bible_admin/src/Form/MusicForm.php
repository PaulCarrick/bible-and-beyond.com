<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Form;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\Core\Form\FormBase;
use Drupal\Core\Form\FormStateInterface;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;
use Symfony\Component\HttpFoundation\File\UploadedFile;

/**
 * Uploads a song of the Christian music section, or changes one (a new file is then optional).
 *
 * The Python tool (ml-service/scripts/manage_music.py) checks everything again, including that the file
 * really is an MP3 or MP4; the checks here only give quicker messages.
 */
class MusicForm extends FormBase {

  private const ID_PATTERN = '/^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$/';

  public function __construct(protected BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_music';
  }

  public function buildForm(array $form, FormStateInterface $form_state, ?string $song_id = NULL): array {
    $form['#cache'] = ['max-age' => 0];
    $song = NULL;
    if ($song_id !== NULL) {
      try {
        $song = $this->manager->getMusic($song_id);
      }
      catch (BibleManagerException $exception) {
        $this->messenger()->addError($exception->getMessage());
        return ['back' => ['#type' => 'link', '#title' => $this->t('Back to the songs'), '#url' => Url::fromRoute('bible_admin.music')]];
      }
      $form_state->set('song_id', $song['id']);
    }
    // The largest file the server takes: the module's own limit, or PHP's when that is lower.
    $limit = min(BibleManager::MAX_MUSIC_BYTES, $this->phpUploadLimit());

    $form['upload_file'] = [
      '#type' => 'file',
      '#title' => $song === NULL ? $this->t('The song file') : $this->t('A new file (optional)'),
      '#description' => ($song === NULL
        ? $this->t('An MP3 (sound) or MP4 (video) file of up to @size MB.', ['@size' => (int) ($limit / 1048576)])
        : $this->t('Leave this empty to keep the present file (@kind, @size MB). An MP3 or MP4 of up to @limit MB replaces it.', [
          '@kind' => $song['kind'] === 'video' ? 'MP4' : 'MP3',
          '@size' => number_format($song['file_size'] / 1048576, 1),
          '@limit' => (int) ($limit / 1048576),
        ])),
      '#attributes' => ['accept' => '.mp3,.mp4,audio/mpeg,video/mp4'],
    ];
    if ($song === NULL) {
      $form['id'] = [
        '#type' => 'textfield',
        '#title' => $this->t('Id'),
        '#description' => $this->t('3 to 50 lowercase letters, digits and hyphens, such as amazing-grace. It names the song in the site\'s addresses and its file. Uploading again with the same id replaces that song.'),
        '#required' => TRUE,
        '#maxlength' => 50,
        '#size' => 30,
      ];
    }
    $form['title'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Title'),
      '#default_value' => $song['title'] ?? '',
      '#required' => TRUE,
      '#maxlength' => 200,
    ];
    $form['author'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Author'),
      '#description' => $this->t('Who wrote it, and who sings or plays it if you wish, for example "John Newton (words), piano by …". Optional.'),
      '#default_value' => $song['author'] ?? '',
      '#maxlength' => 200,
    ];
    $form['lyrics'] = [
      '#type' => 'textarea',
      '#title' => $this->t('Words'),
      '#description' => $this->t('Shown under the player, line by line as typed; leave a blank line between verses. Searched by the search page, even when a words file below is shown instead. Optional (for example for music without words).'),
      '#default_value' => $song['lyrics'] ?? '',
      '#rows' => 16,
    ];
    $form['words_document'] = [
      '#type' => 'file',
      '#title' => $this->t('Words from a PDF, Word document or ebook (optional)'),
      '#description' => !empty($song['lyrics_html'])
        ? $this->t('The words above came from a document, and the music page shows them with its formatting. Choose another document to replace them; changing the words in the box above shows the typed words instead.')
        : $this->t('A PDF (.pdf), Word document (.docx) or EPUB ebook (.epub) of up to @size MB: its text replaces the words above, and the music page shows it with its formatting (headings, bold, italic, lists, pictures). A scanned PDF is read by text recognition.', ['@size' => (int) (BibleManager::MAX_DOCUMENT_BYTES / 1048576)]),
      '#attributes' => ['accept' => '.pdf,.docx,.epub'],
    ];
    $hasWordsFile = !empty($song['words_kind']);
    $form['words_file'] = [
      '#type' => 'file',
      '#title' => $hasWordsFile ? $this->t('A new words file (optional)') : $this->t('The words as a PDF or picture (optional)'),
      '#description' => ($hasWordsFile
        ? $this->t('This song shows its words from a @kind. Leave this empty to keep it, or choose another to replace it.', ['@kind' => $song['words_kind'] === 'pdf' ? 'PDF' : $this->t('picture')])
        : $this->t('For example a scan of the hymnal page: a PDF, PNG, JPEG, WebP or GIF of up to 20 MB. When there is one, the music page shows it in place of the words typed above.')),
      '#attributes' => ['accept' => '.pdf,.png,.jpg,.jpeg,.webp,.gif,application/pdf,image/png,image/jpeg,image/webp,image/gif'],
    ];
    if ($hasWordsFile) {
      $form['remove_words'] = [
        '#type' => 'checkbox',
        '#title' => $this->t('Remove the words file (the typed words are shown again)'),
      ];
    }

    $form['actions'] = ['#type' => 'actions'];
    $form['actions']['submit'] = ['#type' => 'submit', '#value' => $song === NULL ? $this->t('Upload the song') : $this->t('Save')];
    // A link drawn as a button (the admin theme's "button" class), so it sits beside the other button.
    $form['actions']['cancel'] = [
      '#type' => 'link',
      '#title' => $this->t('Cancel'),
      '#url' => Url::fromRoute('bible_admin.music'),
      '#attributes' => ['class' => ['button']],
    ];
    return $form;
  }

  public function validateForm(array &$form, FormStateInterface $form_state): void {
    $isNew = $form_state->get('song_id') === NULL;
    $file = $this->uploadedFile();
    if ($file === NULL) {
      if ($isNew) {
        $form_state->setErrorByName('upload_file', $this->t('Choose an MP3 or MP4 file to upload. (A file larger than the server allows also arrives empty.)'));
      }
    }
    elseif (!$file->isValid()) {
      $form_state->setErrorByName('upload_file', $this->t('The file could not be uploaded: @reason', ['@reason' => $file->getErrorMessage()]));
    }
    elseif (!in_array(strtolower($file->getClientOriginalExtension()), ['mp3', 'mp4'], TRUE)) {
      $form_state->setErrorByName('upload_file', $this->t('The file must be an MP3 (.mp3) or an MP4 (.mp4).'));
    }
    elseif ($file->getSize() > BibleManager::MAX_MUSIC_BYTES) {
      $form_state->setErrorByName('upload_file', $this->t('The file is larger than @size MB.', ['@size' => (int) (BibleManager::MAX_MUSIC_BYTES / 1048576)]));
    }
    $words = $this->uploadedFile('words_file');
    if ($words !== NULL) {
      if (!$words->isValid()) {
        $form_state->setErrorByName('words_file', $this->t('The words file could not be uploaded: @reason', ['@reason' => $words->getErrorMessage()]));
      }
      elseif (!in_array(strtolower($words->getClientOriginalExtension()), ['pdf', 'png', 'jpg', 'jpeg', 'webp', 'gif'], TRUE)) {
        $form_state->setErrorByName('words_file', $this->t('The words file must be a PDF or a picture (.png, .jpg, .webp or .gif).'));
      }
      elseif ($words->getSize() > 20 * 1048576) {
        $form_state->setErrorByName('words_file', $this->t('The words file is larger than 20 MB.'));
      }
    }
    $document = $this->uploadedFile('words_document');
    if ($document !== NULL) {
      if (!$document->isValid()) {
        $form_state->setErrorByName('words_document', $this->t('The document could not be uploaded: @reason', ['@reason' => $document->getErrorMessage()]));
      }
      elseif (!in_array(strtolower($document->getClientOriginalExtension()), ['pdf', 'docx', 'epub'], TRUE)) {
        $form_state->setErrorByName('words_document', $this->t('The document must be a PDF (.pdf), a Word document (.docx) or an EPUB ebook (.epub).'));
      }
      elseif ($document->getSize() > BibleManager::MAX_DOCUMENT_BYTES) {
        $form_state->setErrorByName('words_document', $this->t('The document is larger than @size MB.', ['@size' => (int) (BibleManager::MAX_DOCUMENT_BYTES / 1048576)]));
      }
    }
    if ($isNew && !preg_match(self::ID_PATTERN, strtolower(trim((string) $form_state->getValue('id'))))) {
      $form_state->setErrorByName('id', $this->t('The id must be 3 to 50 lowercase letters, digits and hyphens.'));
    }
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    $songId = $form_state->get('song_id') ?? strtolower(trim((string) $form_state->getValue('id')));
    $details = [
      'title' => trim((string) $form_state->getValue('title')),
      'author' => trim((string) $form_state->getValue('author')),
      'lyrics' => (string) $form_state->getValue('lyrics'),
    ];
    try {
      $song = $this->manager->saveMusic(
        $songId,
        $details,
        $this->uploadedFile(),
        $this->uploadedFile('words_file'),
        (bool) $form_state->getValue('remove_words'),
        $this->uploadedFile('words_document'),
      );
    }
    catch (BibleManagerException $exception) {
      // Stay on the form, with what was typed, so it can be corrected (the file has to be chosen again).
      $this->messenger()->addError($exception->getMessage());
      $form_state->setRebuild();
      return;
    }
    $this->messenger()->addStatus($song['is_published']
      ? $this->t('Saved “@title”.', ['@title' => $song['title']])
      : $this->t('Saved “@title”. It is hidden until you publish it.', ['@title' => $song['title']]));
    $form_state->setRedirect('bible_admin.music');
  }

  private function uploadedFile(string $field = 'upload_file'): ?UploadedFile {
    $files = $this->getRequest()->files->get('files');
    $file = is_array($files) ? ($files[$field] ?? NULL) : NULL;
    return $file instanceof UploadedFile ? $file : NULL;
  }

  /**
   * PHP's own upload limit on this server (upload_max_filesize), in bytes.
   */
  private function phpUploadLimit(): int {
    $value = trim((string) ini_get('upload_max_filesize'));
    $number = (int) $value;
    return match (strtoupper(substr($value, -1))) {
      'G' => $number * 1073741824,
      'M' => $number * 1048576,
      'K' => $number * 1024,
      default => $number,
    };
  }

}
