<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Form;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\bible_admin\Controller\LibraryListController;
use Drupal\Core\Form\ConfirmFormBase;
use Drupal\Core\Form\FormStateInterface;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * Asks before publishing, hiding, deleting or refreshing a commentary or devotional.
 */
class ChangeLibraryForm extends ConfirmFormBase {

  private string $collection = 'commentaries';

  private string $action = '';

  private string $itemId = '';

  private string $name = '';

  public function __construct(protected BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_change_library';
  }

  public function buildForm(array $form, FormStateInterface $form_state, string $collection = 'commentaries', string $action = '', string $item_id = ''): array {
    $this->collection = $collection;
    $this->action = $action;
    $this->itemId = $item_id;
    $this->name = $item_id;
    try {
      foreach ($this->manager->listLibrary($this->kind()) as $item) {
        if ($item['id'] === $item_id) {
          $this->name = $item['name'];
        }
      }
    }
    catch (BibleManagerException) {
      // The question then names it by its id.
    }
    $form = parent::buildForm($form, $form_state);
    if ($action === 'delete') {
      $form['confirm_id'] = [
        '#type' => 'textfield',
        '#title' => $this->t('Type @id to confirm', ['@id' => $item_id]),
        '#required' => TRUE,
        '#size' => 30,
      ];
    }
    return $form;
  }

  private function kind(): string {
    return LibraryListController::COLLECTIONS[$this->collection]['kind'];
  }

  public function getQuestion() {
    return match ($this->action) {
      'publish' => $this->t('Publish @name?', ['@name' => $this->name]),
      'unpublish' => $this->t('Hide @name?', ['@name' => $this->name]),
      'refresh' => $this->t('Refresh @name from its source?', ['@name' => $this->name]),
      default => $this->t('Delete @name?', ['@name' => $this->name]),
    };
  }

  public function getDescription() {
    $isDevotional = $this->kind() === 'devotional';
    if ($this->kind() === 'book') {
      return match ($this->action) {
        'publish' => $this->t('Visitors will see it on the Other books page.'),
        'unpublish' => $this->t('It disappears from the site. Its text stays, and you can publish it again.'),
        'refresh' => $this->t('Its text is downloaded again from Project Gutenberg and replaces the one here, in the background. It stays published or hidden as it is now.'),
        default => $this->t('This permanently removes its text. Visitors\' notes on it stay. A known book can be loaded again with Load; an uploaded one only by uploading its file again.'),
      };
    }
    return match ($this->action) {
      'publish' => $isDevotional
        ? $this->t('Visitors will see it in the devotionals reader, and its daily emails start again.')
        : $this->t('Visitors will see it in the commentaries: the lists, search, the reader and the Commentaries window.'),
      'unpublish' => $isDevotional
        ? $this->t('It disappears from the site and its daily emails pause. Its text stays, and you can publish it again.')
        : $this->t('It disappears from the site everywhere. Its text stays, and you can publish it again.'),
      'refresh' => $this->t('Its text is downloaded again from its source and replaces the one here, in the background (a commentary takes several minutes). It stays published or hidden as it is now.'),
      default => $isDevotional
        ? $this->t('This permanently removes its text and the daily emails people have chosen for it. Visitors\' notes on it stay. A known devotional can be loaded again with Load; an uploaded one only by uploading its file again.')
        : $this->t('This permanently removes its text. Visitors\' notes on it stay. A known commentary can be loaded again with Load; an uploaded one only by uploading its file again.'),
    };
  }

  public function getConfirmText() {
    return match ($this->action) {
      'publish' => $this->t('Publish'),
      'unpublish' => $this->t('Hide'),
      'refresh' => $this->t('Refresh'),
      default => $this->t('Delete'),
    };
  }

  public function getCancelUrl(): Url {
    return Url::fromRoute('bible_admin.library', ['collection' => $this->collection]);
  }

  public function validateForm(array &$form, FormStateInterface $form_state): void {
    if ($this->action === 'delete' && trim((string) $form_state->getValue('confirm_id')) !== $this->itemId) {
      $form_state->setErrorByName('confirm_id', $this->t('Type the id exactly as shown to confirm.'));
    }
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    try {
      $result = $this->manager->changeLibrary($this->kind(), $this->action, $this->itemId);
      $this->messenger()->addStatus(match ($this->action) {
        'publish' => $this->t('@name is now published.', ['@name' => $this->name]),
        'unpublish' => $this->t('@name is now hidden.', ['@name' => $this->name]),
        'refresh' => $this->t('Refreshing @name in the background. This page shows how it is going.', ['@name' => $this->name]),
        default => $this->t('Deleted @name (@count entries@subscriptions).', [
          '@name' => $this->name,
          '@count' => number_format((int) $result['deleted_count']),
          '@subscriptions' => !empty($result['deleted_subscriptions']) ? ', ' . $this->formatPlural((int) $result['deleted_subscriptions'], 'one daily email', '@count daily emails') : '',
        ]),
      });
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
    }
    $form_state->setRedirect('bible_admin.library', ['collection' => $this->collection]);
  }

}
