<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Form;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\Core\Form\FormBase;
use Drupal\Core\Form\FormStateInterface;
use Symfony\Component\DependencyInjection\ContainerInterface;
use Symfony\Component\HttpKernel\Exception\NotFoundHttpException;

/**
 * Step 2: show what the importer found, and import only when the administrator confirms.
 */
class PreviewForm extends FormBase {

  private ?array $upload = NULL;

  public function __construct(protected BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_preview';
  }

  public function buildForm(array $form, FormStateInterface $form_state, string $token = ''): array {
    $upload = $this->loadOwnUpload($token);
    $preview = $upload['preview'];
    $parameters = $upload['meta']['parameters'];
    $canImport = !empty($preview['can_import']);

    $form['#title'] = $this->t('Check @code before importing', ['@code' => $parameters['code']]);
    // Kept in the form state, not in a form value: the Cancel button skips form values.
    $form_state->set('token', $token);

    if (!empty($preview['blocking_errors'])) {
      $form['errors'] = [
        '#theme' => 'item_list',
        '#title' => $this->t('This file cannot be imported'),
        '#items' => array_map(fn ($message) => ['#plain_text' => $message], $preview['blocking_errors']),
        '#attributes' => ['class' => ['messages', 'messages--error']],
      ];
    }
    if (!empty($preview['warnings'])) {
      $form['warnings'] = [
        '#theme' => 'item_list',
        '#title' => $this->t('Please read'),
        '#items' => array_map(fn ($message) => ['#plain_text' => $message], $preview['warnings']),
        '#attributes' => ['class' => ['messages', 'messages--warning']],
      ];
    }

    $existing = $preview['existing'] ?? NULL;
    $afterwards = $existing
      ? ($existing['is_published'] ? $this->t('Stays published, with the new text') : $this->t('Stays hidden, with the new text'))
      : $this->t('Hidden until you publish it');
    $form['summary'] = [
      '#type' => 'table',
      '#caption' => $this->t('What was found'),
      '#header' => [$this->t('Item'), $this->t('Value')],
      '#rows' => [
        [$this->t('Code'), ['data' => ['#plain_text' => $parameters['code']]]],
        [$this->t('Name'), ['data' => ['#plain_text' => $parameters['name']]]],
        [$this->t('License'), ['data' => ['#plain_text' => $parameters['license']]]],
        [$this->t('File format'), ['data' => ['#plain_text' => $preview['format']['name']]]],
        [$this->t('Verses'), number_format((int) $preview['verse_count'])],
        [$this->t('Books'), $this->t('@count of 66', ['@count' => $preview['book_count']])],
        [$this->t('Lines ignored (not verses)'), (string) $preview['skipped_line_count']],
        [$this->t('After importing'), $afterwards],
      ],
    ];

    if (!empty($preview['samples'])) {
      $form['samples'] = [
        '#type' => 'table',
        '#caption' => $this->t('Sample verses. Check that they read correctly.'),
        '#header' => [$this->t('Verse'), $this->t('Text')],
        '#rows' => array_map(
          fn ($sample) => [
            ['data' => ['#plain_text' => $sample['reference']]],
            ['data' => ['#plain_text' => $sample['text']]],
          ],
          $preview['samples'],
        ),
      ];
    }

    if (!empty($preview['books'])) {
      $form['books'] = [
        '#type' => 'details',
        '#title' => $this->t('Books found (@count)', ['@count' => count($preview['books'])]),
        'table' => [
          '#type' => 'table',
          '#header' => [$this->t('Book'), $this->t('Chapters'), $this->t('Verses')],
          '#rows' => array_map(
            fn ($book) => [
              ['data' => ['#plain_text' => $book['name']]],
              (string) $book['chapter_count'],
              (string) $book['verse_count'],
            ],
            $preview['books'],
          ),
        ],
      ];
    }
    if (!empty($preview['missing_books'])) {
      $form['missing'] = [
        '#type' => 'details',
        '#title' => $this->t('Books not in the file (@count)', ['@count' => count($preview['missing_books'])]),
        'list' => ['#plain_text' => implode(', ', $preview['missing_books'])],
      ];
    }
    if (!empty($preview['skipped_line_samples'])) {
      $form['skipped'] = [
        '#type' => 'details',
        '#title' => $this->t('Examples of lines that were ignored'),
        'list' => [
          '#theme' => 'item_list',
          '#items' => array_map(fn ($line) => ['#plain_text' => $line], $preview['skipped_line_samples']),
        ],
      ];
    }

    if ($canImport && $existing) {
      $form['replace_confirmed'] = [
        '#type' => 'checkbox',
        '#title' => $this->t('Yes, replace the existing text of @code', ['@code' => $parameters['code']]),
        '#required' => TRUE,
      ];
    }

    $form['actions'] = ['#type' => 'actions'];
    if ($canImport) {
      $form['actions']['import'] = [
        '#type' => 'submit',
        '#value' => $this->t('Import'),
        '#button_type' => 'primary',
      ];
    }
    $form['actions']['cancel'] = [
      '#type' => 'submit',
      '#value' => $this->t('Cancel and delete the upload'),
      '#submit' => ['::cancel'],
      '#limit_validation_errors' => [],
    ];
    return $form;
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    $token = (string) $form_state->get('token');
    $upload = $this->loadOwnUpload($token);

    try {
      $result = $this->manager->import($upload['path'], $upload['meta']['parameters']);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      $form_state->setRebuild();
      return;
    }

    $this->manager->removeUpload($token);
    $this->messenger()->addStatus($this->t('Imported @count verses as @code. @state', [
      '@count' => number_format((int) $result['verse_count']),
      '@code' => $result['code'],
      '@state' => $result['is_published']
        ? $this->t('It is published.')
        : $this->t('It is hidden. Choose Publish when you are ready for the public to see it.'),
    ]));
    $form_state->setRedirect('bible_admin.list');
  }

  public function cancel(array &$form, FormStateInterface $form_state): void {
    $this->manager->removeUpload((string) $form_state->get('token'));
    $this->messenger()->addStatus($this->t('The upload was deleted.'));
    $form_state->setRedirect('bible_admin.list');
  }

  /**
   * The upload with this token, if it exists and belongs to the current administrator.
   */
  private function loadOwnUpload(string $token): array {
    $upload = $this->manager->loadUpload($token);
    if ($upload === NULL || $upload['preview'] === NULL || (int) $upload['meta']['uid'] !== (int) $this->currentUser()->id()) {
      throw new NotFoundHttpException();
    }
    return $upload;
  }

}
