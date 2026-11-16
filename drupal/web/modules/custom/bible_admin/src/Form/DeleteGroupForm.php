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
 * Asks before deleting a group.
 */
class DeleteGroupForm extends ConfirmFormBase {

  protected ?array $group = NULL;

  public function __construct(protected BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_delete_group';
  }

  public function buildForm(array $form, FormStateInterface $form_state, string $group_id = ''): array {
    try {
      $this->group = $this->manager->getGroup((int) $group_id);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return ['back' => ['#type' => 'link', '#title' => $this->t('Back to the groups'), '#url' => Url::fromRoute('bible_admin.groups')]];
    }
    $form_state->set('group_id', (int) $this->group['id']);
    $form = parent::buildForm($form, $form_state);
    $form['#cache'] = ['max-age' => 0];
    return $form;
  }

  public function getQuestion() {
    return $this->t('Delete the group “@name”?', ['@name' => $this->group['name'] ?? '']);
  }

  public function getDescription() {
    return $this->formatPlural(count($this->group['members'] ?? []),
      'Its one member and the record of what was sent go with it; their site account, if they have one, stays. This cannot be undone.',
      'Its @count members and the record of what was sent go with it; their site accounts, for those who have one, stay. This cannot be undone.');
  }

  public function getConfirmText() {
    return $this->t('Delete');
  }

  public function getCancelUrl(): Url {
    return $this->group ? Url::fromRoute('bible_admin.group', ['group_id' => $this->group['id']]) : Url::fromRoute('bible_admin.groups');
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    try {
      $group = $this->manager->deleteGroup((int) $form_state->get('group_id'));
      $this->messenger()->addStatus($this->t('Deleted the group “@name”.', ['@name' => $group['name']]));
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
    }
    $form_state->setRedirect('bible_admin.groups');
  }

}
