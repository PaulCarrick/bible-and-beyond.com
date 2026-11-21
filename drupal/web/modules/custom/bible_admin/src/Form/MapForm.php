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
 * Uploads a map, or changes one (a new file is then optional).
 *
 * The Python tool (ml-service/scripts/manage_maps.py) checks everything again, including that the file really
 * is a picture or a PDF and that each verse exists; the checks here only give quicker messages.
 */
class MapForm extends FormBase {

  private const ID_PATTERN = '/^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$/';

  public function __construct(protected BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_map';
  }

  public function buildForm(array $form, FormStateInterface $form_state, ?string $map_id = NULL): array {
    $form['#cache'] = ['max-age' => 0];
    $map = NULL;
    if ($map_id !== NULL) {
      try {
        $map = $this->manager->getMap($map_id);
      }
      catch (BibleManagerException $exception) {
        $this->messenger()->addError($exception->getMessage());
        return ['back' => ['#type' => 'link', '#title' => $this->t('Back to the maps'), '#url' => Url::fromRoute('bible_admin.maps')]];
      }
      $form_state->set('map_id', $map['id']);
      $form_state->set('map_kind', $map['kind']);
    }
    $extensions = implode(', ', array_map(fn ($each) => '.' . $each, BibleManager::MAP_EXTENSIONS));

    $form['upload_file'] = [
      '#type' => 'file',
      '#title' => $map === NULL ? $this->t('The map') : $this->t('A new file (optional)'),
      '#description' => $map === NULL
        ? $this->t('A picture (PNG, JPEG, WebP, GIF or TIFF) or a PDF, of up to 1 GB. The site shows a copy of at most 5,000 pixels on its longer side, which can be zoomed into; the file itself is kept on the server and is never offered for download.')
        : $this->t('Leave this empty to keep the present file (@type, @size MB). A new picture or PDF replaces it. Members\' pins and routes are kept where they were across and down the map, so replace it only with the same map (a sharper scan, say).', [
          '@type' => $map['file_type'],
          '@size' => number_format($map['file_size'] / 1048576, 1),
        ]),
      '#attributes' => ['accept' => implode(',', array_map(fn ($each) => '.' . $each, BibleManager::MAP_EXTENSIONS))],
      // A "Paste a picture" box under the field (js/paste-picture.js).
      '#attached' => ['library' => ['bible_admin/paste_picture']],
    ];
    $form['pdf_page'] = [
      '#type' => 'number',
      '#title' => $this->t('Page of a PDF'),
      '#description' => $this->t('For a PDF: the page drawn as the map (the first is 1). Ignored for a picture.'),
      '#default_value' => $map['pdf_page'] ?? 1,
      '#min' => 1,
      '#max' => 10000,
      '#size' => 6,
    ];
    if ($map === NULL) {
      $form['id'] = [
        '#type' => 'textfield',
        '#title' => $this->t('Id'),
        '#description' => $this->t('3 to 50 lowercase letters, digits and hyphens, such as pauls-first-journey. It names the map in the site\'s addresses and its files. Uploading again with the same id replaces that map.'),
        '#required' => TRUE,
        '#maxlength' => 50,
        '#size' => 30,
      ];
    }
    $form['title'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Title'),
      '#default_value' => $map['title'] ?? '',
      '#required' => TRUE,
      '#maxlength' => 200,
    ];
    $form['description'] = [
      '#type' => 'textarea',
      '#title' => $this->t('Description'),
      '#description' => $this->t('Shown beside the map, as typed (a blank line between paragraphs). Searched. Optional.'),
      '#default_value' => $map['description'] ?? '',
      '#rows' => 6,
    ];
    $form['source'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Where it came from'),
      '#description' => $this->t('The map\'s source and its credit or licence line, shown under it, for example "Public domain, from the 1901 Bible Atlas". Optional.'),
      '#default_value' => $map['source'] ?? '',
      '#maxlength' => 500,
    ];
    $form['keywords'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Keywords'),
      '#description' => $this->t('Words or phrases, separated by commas, that a visitor might search for and that are not in the title or description, for example "Exodus, wilderness, Sinai". Optional.'),
      '#default_value' => $map['keywords'] ?? '',
      '#maxlength' => 500,
    ];
    $form['verses'] = [
      '#type' => 'textarea',
      '#title' => $this->t('Verses'),
      '#description' => $this->t('The Bible verses this map goes with, separated by semicolons or on separate lines, for example "Acts 13:4-14; Acts 14:26". A range stays inside one chapter. Each must be a verse that exists; the map is not saved otherwise. The site links each one to the Bible reader, and lists this map for any verse in them. Optional.'),
      '#default_value' => $map['verses_text'] ?? '',
      '#rows' => 3,
    ];

    $form['actions'] = ['#type' => 'actions'];
    $form['actions']['submit'] = ['#type' => 'submit', '#value' => $map === NULL ? $this->t('Upload the map') : $this->t('Save')];
    // A link drawn as a button (the admin theme's "button" class), so it sits beside the other button.
    $form['actions']['cancel'] = [
      '#type' => 'link',
      '#title' => $this->t('Cancel'),
      '#url' => Url::fromRoute('bible_admin.maps'),
      '#attributes' => ['class' => ['button']],
    ];
    return $form;
  }

  public function validateForm(array &$form, FormStateInterface $form_state): void {
    $isNew = $form_state->get('map_id') === NULL;
    $file = $this->uploadedFile();
    if ($file === NULL) {
      if ($isNew) {
        $form_state->setErrorByName('upload_file', $this->t('Choose a picture or a PDF to upload. (A file larger than the server allows also arrives empty.)'));
      }
    }
    elseif (!$file->isValid()) {
      $form_state->setErrorByName('upload_file', $this->t('The file could not be uploaded: @reason', ['@reason' => $file->getErrorMessage()]));
    }
    elseif (!in_array(strtolower($file->getClientOriginalExtension()), BibleManager::MAP_EXTENSIONS, TRUE)) {
      $form_state->setErrorByName('upload_file', $this->t('The map must be a picture (.png, .jpg, .webp, .gif, .tif) or a PDF (.pdf).'));
    }
    elseif ($file->getSize() > BibleManager::MAX_MAP_BYTES) {
      $form_state->setErrorByName('upload_file', $this->t('The file is larger than 1 GB.'));
    }
    if ($isNew && !preg_match(self::ID_PATTERN, strtolower(trim((string) $form_state->getValue('id'))))) {
      $form_state->setErrorByName('id', $this->t('The id must be 3 to 50 lowercase letters, digits and hyphens.'));
    }
    $page = $form_state->getValue('pdf_page');
    if ($page !== '' && $page !== NULL && (!ctype_digit((string) $page) || (int) $page < 1)) {
      $form_state->setErrorByName('pdf_page', $this->t('The page must be a number from 1.'));
    }
    // The verses, read as the site reads them, so a mistake is shown before the file is sent on.
    $verses = trim((string) $form_state->getValue('verses'));
    if ($verses !== '' && !$form_state->hasAnyErrors()) {
      try {
        $this->manager->checkMapVerses($verses);
      }
      catch (BibleManagerException $exception) {
        $form_state->setErrorByName('verses', $exception->getMessage());
      }
    }
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    $mapId = $form_state->get('map_id') ?? strtolower(trim((string) $form_state->getValue('id')));
    $details = [
      'title' => trim((string) $form_state->getValue('title')),
      'description' => (string) $form_state->getValue('description'),
      'source' => trim((string) $form_state->getValue('source')),
      'keywords' => trim((string) $form_state->getValue('keywords')),
      'verses' => (string) $form_state->getValue('verses'),
    ];
    $file = $this->uploadedFile();
    $page = (int) ($form_state->getValue('pdf_page') ?: 1);
    // A page only matters for a PDF: a new PDF, or the map's own PDF when no new file is sent.
    $isPdf = $file !== NULL ? strtolower($file->getClientOriginalExtension()) === 'pdf' : $form_state->get('map_kind') === 'pdf';
    try {
      $map = $this->manager->saveMap($mapId, $details, $file, $isPdf ? $page : NULL);
    }
    catch (BibleManagerException $exception) {
      // Stay on the form, with what was typed, so it can be corrected (the file has to be chosen again).
      $this->messenger()->addError($exception->getMessage());
      $form_state->setRebuild();
      return;
    }
    $this->messenger()->addStatus($map['is_published']
      ? $this->t('Saved “@title”.', ['@title' => $map['title']])
      : $this->t('Saved “@title”. It is hidden until you publish it.', ['@title' => $map['title']]));
    $form_state->setRedirect('bible_admin.maps');
  }

  private function uploadedFile(): ?UploadedFile {
    $files = $this->getRequest()->files->get('files');
    $file = is_array($files) ? ($files['upload_file'] ?? NULL) : NULL;
    return $file instanceof UploadedFile ? $file : NULL;
  }

}
