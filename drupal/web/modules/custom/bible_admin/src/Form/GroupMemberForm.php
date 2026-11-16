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
 * Adds a member to a group by email address (the site account with it, else a contact with the name typed),
 * or changes a contact's name, address and phone.
 */
class GroupMemberForm extends FormBase {

  public function __construct(protected BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_group_member';
  }

  public function buildForm(array $form, FormStateInterface $form_state, string $group_id = '', ?string $member_id = NULL): array {
    $form['#cache'] = ['max-age' => 0];
    try {
      $group = $this->manager->getGroup((int) $group_id);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return ['back' => ['#type' => 'link', '#title' => $this->t('Back to the groups'), '#url' => Url::fromRoute('bible_admin.groups')]];
    }
    $member = NULL;
    if ($member_id !== NULL) {
      foreach ($group['members'] as $each) {
        if ((int) $each['id'] === (int) $member_id) {
          $member = $each;
        }
      }
      if ($member === NULL || $member['is_account']) {
        $this->messenger()->addError($member === NULL
          ? $this->t('That member is not in the group (they may have been removed).')
          : $this->t('This member has an account on the site; they change their own details on My account.'));
        return ['back' => ['#type' => 'link', '#title' => $this->t('Back to the group'), '#url' => Url::fromRoute('bible_admin.group', ['group_id' => $group['id']])]];
      }
      $form_state->set('member_id', (int) $member['id']);
    }
    $form_state->set('group_id', (int) $group['id']);

    if ($member === NULL) {
      $form['intro'] = [
        '#type' => 'html_tag',
        '#tag' => 'p',
        '#value' => $this->t('Adding to “@group”. If the address belongs to an account on the site, that account is added and the name and phone here are not needed: they get your messages the way they chose on My account (email, text or both). Anyone else is added as a contact with the name you type, and gets email only.', ['@group' => $group['name']]),
      ];
    }
    $form['email'] = [
      '#type' => 'email',
      '#title' => $this->t('Email address'),
      '#default_value' => $member['email'] ?? '',
      '#required' => TRUE,
    ];
    $form['name'] = [
      '#type' => 'textfield',
      '#title' => $member === NULL ? $this->t('Name (needed if they have no account)') : $this->t('Name'),
      '#default_value' => $member['name'] ?? '',
      '#maxlength' => 200,
      '#required' => $member !== NULL,
    ];
    $form['phone'] = [
      '#type' => 'tel',
      '#title' => $this->t('Phone (optional, for your reference)'),
      '#default_value' => $member['phone'] ?? '',
      '#maxlength' => 40,
      '#description' => $this->t('Contacts are never texted: texts go only to site accounts whose owners asked for them.'),
    ];
    $form['actions'] = ['#type' => 'actions'];
    $form['actions']['submit'] = ['#type' => 'submit', '#value' => $member === NULL ? $this->t('Add') : $this->t('Save')];
    if ($member === NULL) {
      $form['actions']['another'] = ['#type' => 'submit', '#value' => $this->t('Add and add another'), '#submit' => ['::submitAndAnother']];
    }
    $form['actions']['cancel'] = [
      '#type' => 'link',
      '#title' => $this->t('Cancel'),
      '#url' => Url::fromRoute('bible_admin.group', ['group_id' => $group['id']]),
      '#attributes' => ['class' => ['button']],
    ];
    return $form;
  }

  private function save(FormStateInterface $form_state): ?array {
    $groupId = (int) $form_state->get('group_id');
    $memberId = $form_state->get('member_id');
    $details = [
      'email' => (string) $form_state->getValue('email'),
      'name' => (string) $form_state->getValue('name'),
      'phone' => (string) $form_state->getValue('phone'),
    ];
    try {
      return $memberId === NULL
        ? $this->manager->addGroupMember($groupId, $details)
        : $this->manager->updateGroupMember($groupId, (int) $memberId, $details);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      $form_state->setRebuild();
      return NULL;
    }
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    $member = $this->save($form_state);
    if ($member === NULL) {
      return;
    }
    $this->messenger()->addStatus($this->t('@name: @how.', ['@name' => $member['name'] ?: $member['email'], '@how' => $member['is_account'] ? $this->t('added (site account; gets messages by @receives)', ['@receives' => mb_strtolower($member['receives'])]) : $this->t('saved')]));
    $form_state->setRedirect('bible_admin.group', ['group_id' => (int) $form_state->get('group_id')]);
  }

  /**
   * Add, then the empty form again for the next person.
   */
  public function submitAndAnother(array &$form, FormStateInterface $form_state): void {
    $member = $this->save($form_state);
    if ($member === NULL) {
      return;
    }
    $this->messenger()->addStatus($this->t('Added @name.', ['@name' => $member['name'] ?: $member['email']]));
    $form_state->setRedirect('bible_admin.group_member_add', ['group_id' => (int) $form_state->get('group_id')]);
  }

}
