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
 * Adds a Kindle book to the Devotionals or the Other books, or changes one: a title, an author, the link to the book
 * in Amazon's Kindle web reader, whether the site lists it, and an optional picture (kindle_books.py checks them).
 */
class KindleBookForm extends FormBase {

  private const COLLECTIONS = ['devotionals' => 'Devotionals', 'books' => 'Other books'];

  /**
   * Largest picture, in bytes (kindle_books.MAX_COVER_BYTES).
   */
  private const MAX_COVER_BYTES = 2 * 1024 * 1024;

  private const COVER_EXTENSIONS = ['png', 'jpg', 'jpeg', 'webp', 'gif'];

  public function __construct(protected BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_kindle_book';
  }

  public function buildForm(array $form, FormStateInterface $form_state, string $collection = 'books', ?string $book_id = NULL): array {
    $form['#cache'] = ['max-age' => 0];
    $form_state->set('collection', $collection);
    $back = Url::fromRoute('bible_admin.library', ['collection' => $collection]);
    $book = NULL;
    if ($book_id !== NULL) {
      try {
        $book = $this->manager->getKindleBook((int) $book_id);
      }
      catch (BibleManagerException $exception) {
        $this->messenger()->addError($exception->getMessage());
        return ['back' => ['#type' => 'link', '#title' => $this->t('Back'), '#url' => $back]];
      }
      $form_state->set('book_id', (int) $book['id']);
    }
    $form['intro'] = [
      '#type' => 'html_tag',
      '#tag' => 'p',
      '#value' => $this->t('A book read in Amazon’s Kindle web reader, listed with the @collection. Only the link is kept here: each reader opens it signed in to their own Amazon account, so it works only for those who have the book in their own Kindle library, and its words cannot be searched on this site.', ['@collection' => self::COLLECTIONS[$collection]]),
    ];
    $form['title'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Title'),
      '#default_value' => $book['title'] ?? '',
      '#maxlength' => 300,
      '#required' => TRUE,
    ];
    $form['author'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Author (optional)'),
      '#default_value' => $book['author'] ?? '',
      '#maxlength' => 200,
    ];
    $form['address'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Kindle link'),
      '#default_value' => $book['address'] ?? '',
      '#maxlength' => 2000,
      '#required' => TRUE,
      '#placeholder' => 'https://read.amazon.com/?asin=B00DL10JF6',
      '#description' => $this->t('Open the book in the Kindle web reader (read.amazon.com) and copy the address from the browser’s address bar. It must be an amazon.com address.'),
    ];
    $form['is_published'] = [
      '#type' => 'checkbox',
      '#title' => $this->t('Show it on the site'),
      '#default_value' => $book['is_published'] ?? TRUE,
      '#description' => $this->t('Clear it to hide the book from the site without deleting it.'),
    ];
    $form['picture'] = [
      '#type' => 'fieldset',
      '#title' => $this->t('Picture (optional)'),
    ];
    if (!empty($book['cover_data_uri'])) {
      $form['picture']['preview'] = [
        '#type' => 'html_tag',
        '#tag' => 'img',
        '#attributes' => [
          'src' => $book['cover_data_uri'],
          'alt' => $this->t('The picture in use'),
          'style' => 'max-width: 160px; max-height: 220px; border: 1px solid #ccc; padding: 4px; background: #fff; display: block; margin-bottom: 8px;',
        ],
      ];
    }
    $form['picture']['cover'] = [
      '#type' => 'file',
      '#title' => empty($book['cover']) ? $this->t('Upload a picture') : $this->t('Upload a different picture'),
      '#description' => $this->t('Shown beside the book on the site, such as its cover. PNG, JPEG, WebP or GIF, up to @size MB. Leave empty to keep the one in use.', ['@size' => self::MAX_COVER_BYTES / (1024 * 1024)]),
      '#attributes' => ['accept' => '.png,.jpg,.jpeg,.webp,.gif'],
      // A "Paste a picture" box under the field (js/paste-picture.js).
      '#attached' => ['library' => ['bible_admin/paste_picture']],
    ];
    if (!empty($book['cover'])) {
      $form['picture']['remove_cover'] = [
        '#type' => 'checkbox',
        '#title' => $this->t('Remove the picture'),
      ];
    }
    $form['actions'] = ['#type' => 'actions'];
    $form['actions']['submit'] = ['#type' => 'submit', '#value' => $book === NULL ? $this->t('Add the book') : $this->t('Save')];
    $form['actions']['cancel'] = ['#type' => 'link', '#title' => $this->t('Cancel'), '#url' => $back, '#attributes' => ['class' => ['button']]];
    return $form;
  }

  /**
   * The picture chosen in the upload field, or NULL when none was.
   */
  private function uploadedCover(): ?UploadedFile {
    $files = $this->getRequest()->files->get('files');
    $file = is_array($files) ? ($files['cover'] ?? NULL) : NULL;
    return $file instanceof UploadedFile ? $file : NULL;
  }

  public function validateForm(array &$form, FormStateInterface $form_state): void {
    $file = $this->uploadedCover();
    if ($file === NULL) {
      return;
    }
    if (!$file->isValid()) {
      $form_state->setErrorByName('cover', $this->t('The picture could not be uploaded: @reason', ['@reason' => $file->getErrorMessage()]));
    }
    elseif (!in_array(strtolower($file->getClientOriginalExtension()), self::COVER_EXTENSIONS, TRUE)) {
      $form_state->setErrorByName('cover', $this->t('The picture must be a PNG, JPEG, WebP or GIF file.'));
    }
    elseif ($file->getSize() > self::MAX_COVER_BYTES) {
      $form_state->setErrorByName('cover', $this->t('The picture is larger than @size MB.', ['@size' => self::MAX_COVER_BYTES / (1024 * 1024)]));
    }
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    $bookId = $form_state->get('book_id');
    $collection = (string) $form_state->get('collection');
    try {
      $book = $this->manager->saveKindleBook(
        $bookId === NULL ? NULL : (int) $bookId,
        $collection,
        (string) $form_state->getValue('title'),
        (string) $form_state->getValue('author'),
        (string) $form_state->getValue('address'),
        (bool) $form_state->getValue('is_published'),
      );
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      $form_state->setRebuild();
      return;
    }
    // The picture, once the book is saved (a new book has its id only now).
    try {
      $file = $this->uploadedCover();
      if ($file !== NULL) {
        $book = $this->manager->saveKindleCover((int) $book['id'], $file);
      }
      elseif ($form_state->getValue('remove_cover')) {
        $book = $this->manager->removeKindleCover((int) $book['id']);
      }
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($this->t('“@title” was saved, but not its picture: @message', ['@title' => $book['title'], '@message' => $exception->getMessage()]));
      $form_state->setRedirect('bible_admin.kindle_book_edit', ['collection' => $collection, 'book_id' => $book['id']]);
      return;
    }
    $this->messenger()->addStatus($bookId === NULL
      ? $this->t('Added “@title”.', ['@title' => $book['title']])
      : $this->t('Saved “@title”.', ['@title' => $book['title']]));
    $form_state->setRedirect('bible_admin.library', ['collection' => $collection]);
  }

}
