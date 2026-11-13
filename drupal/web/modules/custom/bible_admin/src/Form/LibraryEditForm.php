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

/**
 * Changes the details of a commentary, devotional or Other book: its name, its short name or author, its
 * translator, its source and its credit line. The text and the published state stay as they are.
 *
 * The Python tool (ml-service/scripts/manage_library.py update) checks everything again.
 */
class LibraryEditForm extends FormBase {

  public function __construct(protected BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_library_edit';
  }

  public function buildForm(array $form, FormStateInterface $form_state, string $collection = 'books', string $item_id = ''): array {
    $form['#cache'] = ['max-age' => 0];
    $about = LibraryListController::COLLECTIONS[$collection];
    $back = Url::fromRoute('bible_admin.library', ['collection' => $collection]);
    try {
      $item = $this->manager->getLibraryItem($about['kind'], $item_id);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return ['back' => ['#type' => 'link', '#title' => $this->t('Back to the list'), '#url' => $back]];
    }
    $form_state->set('collection', $collection);
    $form_state->set('item_id', $item['id']);
    $isCommentary = $about['kind'] === 'commentary';

    $form['about'] = [
      '#type' => 'html_tag',
      '#tag' => 'p',
      '#value' => $this->t('The @one %id (@status). Only its details change here; its text stays as it is.', [
        '@one' => $about['one'],
        '%id' => $item['id'],
        '@status' => $item['is_published'] ? $this->t('published') : $this->t('hidden'),
      ]) . ' ' . ($item['refreshable']
        ? $this->t('It is loaded from its source, so Refresh puts back the details from there.')
        : $this->t('Uploading its file again replaces these details with the ones typed on the Upload form.')),
    ];
    $form['name'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Name'),
      '#default_value' => $item['name'],
      '#required' => TRUE,
      '#maxlength' => 200,
    ];
    if ($isCommentary) {
      $form['short_name'] = [
        '#type' => 'textfield',
        '#title' => $this->t('Short name'),
        '#description' => $this->t('Used on the tabs of the Commentaries window, such as Matthew Henry.'),
        '#default_value' => $item['short_name'],
        '#required' => TRUE,
        '#maxlength' => 40,
      ];
    }
    else {
      $form['author'] = [
        '#type' => 'textfield',
        '#title' => $this->t('Author'),
        '#default_value' => $item['author'],
        '#required' => TRUE,
        '#maxlength' => 200,
      ];
      $form['translator'] = [
        '#type' => 'textfield',
        '#title' => $this->t('Translator (optional)'),
        '#default_value' => $item['translator'],
        '#maxlength' => 200,
      ];
    }
    $form['source_name'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Source'),
      '#description' => $this->t('Where the text comes from, such as Project Gutenberg. It is named in the credit.'),
      '#default_value' => $item['source_name'],
      '#required' => TRUE,
      '#maxlength' => 200,
    ];
    $form['source_url'] = [
      '#type' => 'url',
      '#title' => $this->t('Source address (optional)'),
      '#default_value' => $item['source_url'],
      '#maxlength' => 500,
    ];
    if ($isCommentary) {
      $form['license_url'] = [
        '#type' => 'url',
        '#title' => $this->t('License address'),
        '#description' => $this->t('Empty for the Public Domain Mark.'),
        '#default_value' => $item['license_url'],
        '#maxlength' => 500,
      ];
    }
    else {
      $form['credit'] = [
        '#type' => 'textfield',
        '#title' => $this->t('Credit line (optional)'),
        '#description' => $this->t('Shown under the text instead of "... is in the public domain", for a text that is not an old public-domain edition. Empty for the usual line.'),
        '#default_value' => $item['credit'],
        '#maxlength' => 500,
      ];
    }
    $form['actions'] = [
      '#type' => 'actions',
      'submit' => ['#type' => 'submit', '#value' => $this->t('Save'), '#button_type' => 'primary'],
      'cancel' => [
        '#type' => 'link',
        '#title' => $this->t('Cancel'),
        '#url' => $back,
        '#attributes' => ['class' => ['button']],
      ],
    ];
    return $form;
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    $collection = $form_state->get('collection');
    $about = LibraryListController::COLLECTIONS[$collection];
    $fields = $about['kind'] === 'commentary'
      ? ['name', 'short_name', 'source_name', 'source_url', 'license_url']
      : ['name', 'author', 'translator', 'source_name', 'source_url', 'credit'];
    $details = [];
    foreach ($fields as $field) {
      $details[$field] = trim((string) $form_state->getValue($field));
    }
    try {
      $item = $this->manager->updateLibraryItem($about['kind'], $form_state->get('item_id'), $details);
    }
    catch (BibleManagerException $exception) {
      // Stay on the form, with what was typed, so it can be corrected.
      $this->messenger()->addError($exception->getMessage());
      $form_state->setRebuild();
      return;
    }
    $this->messenger()->addStatus($this->t('Saved the details of “@name”.', ['@name' => $item['name']]));
    $form_state->setRedirect('bible_admin.library', ['collection' => $collection]);
  }

}
