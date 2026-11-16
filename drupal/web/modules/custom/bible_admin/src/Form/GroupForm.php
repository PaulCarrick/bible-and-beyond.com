<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Form;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\Core\Form\FormBase;
use Drupal\Core\Form\FormStateInterface;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * Makes a group (led by the user making it) or changes its name and description.
 */
class GroupForm extends FormBase {

  public function __construct(protected BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_group';
  }

  public function buildForm(array $form, FormStateInterface $form_state, ?string $group_id = NULL): array {
    $form['#cache'] = ['max-age' => 0];
    $group = NULL;
    if ($group_id !== NULL) {
      try {
        $group = $this->manager->getGroup((int) $group_id);
      }
      catch (BibleManagerException $exception) {
        $this->messenger()->addError($exception->getMessage());
        return ['back' => ['#type' => 'link', '#title' => $this->t('Back to the groups'), '#url' => Url::fromRoute('bible_admin.groups')]];
      }
      $form_state->set('group_id', (int) $group['id']);
    }
    $form['name'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Name'),
      '#default_value' => $group['name'] ?? '',
      '#maxlength' => 200,
      '#required' => TRUE,
      '#description' => $this->t('Shown in the subject of verse cards and at the foot of every email, such as “Smith family care group”.'),
    ];
    $form['description'] = [
      '#type' => 'textarea',
      '#title' => $this->t('Notes (only you see them)'),
      '#default_value' => $group['description'] ?? '',
      '#rows' => 3,
      '#maxlength' => 2000,
    ];
    $form['actions'] = ['#type' => 'actions'];
    $form['actions']['submit'] = ['#type' => 'submit', '#value' => $group === NULL ? $this->t('Make the group') : $this->t('Save')];
    $form['actions']['cancel'] = [
      '#type' => 'link',
      '#title' => $this->t('Cancel'),
      '#url' => $group === NULL ? Url::fromRoute('bible_admin.groups') : Url::fromRoute('bible_admin.group', ['group_id' => $group['id']]),
      '#attributes' => ['class' => ['button']],
    ];
    return $form;
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    $groupId = $form_state->get('group_id');
    try {
      $group = $this->manager->saveGroup($groupId === NULL ? NULL : (int) $groupId, (string) $form_state->getValue('name'), (string) $form_state->getValue('description'));
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      $form_state->setRebuild();
      return;
    }
    $this->messenger()->addStatus($groupId === NULL
      ? $this->t('Made the group “@name”. Now add its members.', ['@name' => $group['name']])
      : $this->t('Saved “@name”.', ['@name' => $group['name']]));
    $form_state->setRedirect('bible_admin.group', ['group_id' => $group['id']]);
  }

}
