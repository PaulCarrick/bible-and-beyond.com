<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Form;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\bible_admin\GroupEditor;
use Drupal\Core\Entity\EntityTypeManagerInterface;
use Drupal\Core\Form\FormBase;
use Drupal\Core\Form\FormStateInterface;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * Makes a group (led by the user making it) or changes its name and description; someone who administers all
 * groups can also give it another leader (the owner's request, 2026-11-16).
 */
class GroupForm extends FormBase {

  public function __construct(protected BibleManager $manager, protected EntityTypeManagerInterface $entityTypes) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'), $container->get('entity_type.manager'));
  }

  /**
   * The Drupal users who can lead groups (active, with "lead groups" or "administer groups"), by name, and the
   * group's own leader in any case.
   */
  protected function leaderOptions(int $currentLeader): array {
    $options = [];
    foreach ($this->entityTypes->getStorage('user')->loadByProperties(['status' => 1]) as $user) {
      if ($user->id() && ((int) $user->id() === $currentLeader || $user->hasPermission('lead groups') || $user->hasPermission('administer groups'))) {
        $options[(int) $user->id()] = $user->getDisplayName() . ($user->getEmail() ? ' (' . $user->getEmail() . ')' : '');
      }
    }
    natcasesort($options);
    return $options;
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
    // The Description (2026-11-27, the owner's request): one line, the title of the group's sign-up sheet.
    $form['headline'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Description'),
      '#default_value' => $group['headline'] ?? '',
      '#maxlength' => 120,
      '#description' => $this->t('One line, such as “After Church Fellowship Time - Thank you for Serving the Body”. It is the title of the group’s sign-up sheet (Scheduled tasks); with none, the name is used.'),
    ];
    if ($group !== NULL && $this->currentUser()->hasPermission('administer groups')) {
      $form['leader'] = [
        '#type' => 'select',
        '#title' => $this->t('Leader'),
        '#options' => $this->leaderOptions((int) $group['owner_uid']),
        '#default_value' => (int) $group['owner_uid'],
        '#required' => TRUE,
        '#description' => $this->t('The group moves to the person chosen: only they (and those who administer all groups) see it, and replies to its emails go to their address. The list holds the Drupal users who can lead groups; give someone the Group leader role to add them.'),
      ];
    }
    // The editor (GroupEditor; the owner's request, 2026-11-17).
    $form['description'] = GroupEditor::field((string) $this->t('Notes (only the leader and those who administer all groups see them)'), (string) ($group['description'] ?? ''), 3, FALSE);
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
      $leaderId = $form_state->getValue('leader');
      $leader = $leaderId ? $this->entityTypes->getStorage('user')->load((int) $leaderId) : NULL;
      $group = $this->manager->saveGroup($groupId === NULL ? NULL : (int) $groupId, (string) $form_state->getValue('name'), GroupEditor::value($form_state->getValue('description')), $leader, (string) $form_state->getValue('headline'));
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
