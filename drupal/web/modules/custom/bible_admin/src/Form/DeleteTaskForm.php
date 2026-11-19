<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Form;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\Core\Form\ConfirmFormBase;
use Drupal\Core\Form\FormStateInterface;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * Asks before deleting a task.
 */
class DeleteTaskForm extends ConfirmFormBase {

  private ?array $task = NULL;

  public function __construct(private readonly BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_delete_task';
  }

  public function buildForm(array $form, FormStateInterface $form_state, ?string $task_id = NULL): array {
    try {
      $this->task = $this->manager->getTask((int) $task_id);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return ['back' => ['#type' => 'link', '#title' => $this->t('Back to the tasks'), '#url' => $this->getCancelUrl()]];
    }
    $form_state->set('task_id', (int) $this->task['id']);
    $form = parent::buildForm($form, $form_state);
    $form['#cache'] = ['max-age' => 0];
    return $form;
  }

  public function getQuestion() {
    return $this->t('Delete the task “@name”?', ['@name' => $this->task['name'] ?? '']);
  }

  public function getDescription() {
    return $this->t('Its description and both notifications are deleted with it. This cannot be undone.');
  }

  public function getConfirmText() {
    return $this->t('Delete');
  }

  public function getCancelUrl(): Url {
    return Url::fromRoute('bible_admin.tasks');
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    try {
      $task = $this->manager->deleteTask((int) $form_state->get('task_id'));
      $this->messenger()->addStatus($this->t('Deleted the task “@name”.', ['@name' => $task['name']]));
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
    }
    $form_state->setRedirect('bible_admin.tasks');
  }

}
