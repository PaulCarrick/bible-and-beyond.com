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
 * Step 2 of uploading a commentary or devotional: show what was found, then import or cancel.
 */
class LibraryPreviewForm extends FormBase {

  public function __construct(protected BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_library_preview';
  }

  public function buildForm(array $form, FormStateInterface $form_state, string $collection = 'commentaries', string $token = ''): array {
    $upload = $this->loadOwnUpload($collection, $token);
    $preview = $upload['preview'];
    $parameters = $upload['meta']['parameters'];
    $summary = $preview['summary'];
    $isCommentary = $collection === 'commentaries';
    $canImport = !empty($preview['can_import']);

    $form['#title'] = $this->t('Check @name before importing', ['@name' => $parameters['name']]);
    // Kept in the form state, not in a form value: the Cancel button skips form values.
    $form_state->set('token', $token);
    $form_state->set('collection', $collection);

    if (!empty($preview['problems'])) {
      $form['errors'] = [
        '#theme' => 'item_list',
        '#title' => $this->t('This file cannot be imported'),
        '#items' => array_map(fn ($message) => ['#plain_text' => $message], $preview['problems']),
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
    $rows = [
      [$this->t('Id'), ['data' => ['#plain_text' => $preview['details']['id']]]],
      [$this->t('Name'), ['data' => ['#plain_text' => $preview['details']['name']]]],
      [$this->t('Where the text came from'), ['data' => ['#plain_text' => $preview['details']['source_name']]]],
    ];
    if ($isCommentary) {
      $rows[] = [$this->t('Notes'), number_format((int) $summary['notes'])];
      $rows[] = [$this->t('Introductions'), number_format((int) $summary['introductions'])];
      $rows[] = [$this->t('Books'), ['data' => ['#plain_text' => implode(', ', $summary['books'])]]];
    }
    else {
      $rows[] = [$this->t('Days or chapters'), number_format((int) $summary['units'])];
      $rows[] = [$this->t('Readings'), number_format((int) $summary['readings'])];
      $rows[] = [$this->t('Sections'), ['data' => ['#plain_text' => implode(', ', $summary['sections'])]]];
    }
    if ($existing) {
      $rows[] = [$this->t('Now in the site'), $this->t('@count entries, which this replaces', ['@count' => number_format((int) $existing['count'])])];
    }
    $rows[] = [$this->t('After importing'), $afterwards];
    $form['summary'] = [
      '#type' => 'table',
      '#caption' => $this->t('What was found'),
      '#header' => [$this->t('Item'), $this->t('Value')],
      '#rows' => $rows,
    ];

    if (!empty($summary['samples'])) {
      $form['samples'] = [
        '#type' => 'table',
        '#caption' => $this->t('The first entries. Check that they read correctly.'),
        '#header' => [$this->t('Where'), $this->t('Text')],
        '#rows' => array_map(
          fn ($sample) => [['data' => ['#plain_text' => $sample['place']]], ['data' => ['#plain_text' => $sample['text']]]],
          $summary['samples'],
        ),
      ];
    }

    if ($canImport && $existing) {
      $form['replace_confirmed'] = [
        '#type' => 'checkbox',
        '#title' => $this->t('Yes, replace the text of @id', ['@id' => $preview['details']['id']]),
        '#required' => TRUE,
      ];
    }

    $form['actions'] = ['#type' => 'actions'];
    if ($canImport) {
      $form['actions']['import'] = ['#type' => 'submit', '#value' => $this->t('Import'), '#button_type' => 'primary'];
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
    $collection = (string) $form_state->get('collection');
    $upload = $this->loadOwnUpload($collection, $token);
    try {
      $result = $this->manager->importLibrary($upload['path'], $upload['meta']['parameters']);
      $this->messenger()->addStatus($result['is_published']
        ? $this->t('Imported @name (@count entries). It is published.', ['@name' => $result['name'], '@count' => number_format((int) $result['count'])])
        : $this->t('Imported @name (@count entries). It is hidden until you publish it.', ['@name' => $result['name'], '@count' => number_format((int) $result['count'])]));
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return;
    }
    $this->manager->removeUpload($token);
    $form_state->setRedirect('bible_admin.library', ['collection' => $collection]);
  }

  public function cancel(array &$form, FormStateInterface $form_state): void {
    $this->manager->removeUpload((string) $form_state->get('token'));
    $this->messenger()->addStatus($this->t('The upload was deleted.'));
    $form_state->setRedirect('bible_admin.library', ['collection' => (string) $form_state->get('collection')]);
  }

  /**
   * The upload with this token, if it exists, is for this collection and belongs to the current administrator.
   */
  private function loadOwnUpload(string $collection, string $token): array {
    $upload = $this->manager->loadUpload($token);
    if ($upload === NULL || $upload['preview'] === NULL
      || (int) $upload['meta']['uid'] !== (int) $this->currentUser()->id()
      || ($upload['meta']['parameters']['collection'] ?? '') !== $collection) {
      throw new NotFoundHttpException();
    }
    return $upload;
  }

}
