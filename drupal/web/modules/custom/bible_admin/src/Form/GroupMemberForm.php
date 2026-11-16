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
 * Adds members to a group, or changes a contact's name, address and phone.
 *
 * Adding (the owner's request, 2026-11-16): "People with an account on the site" (the default) is a list of the
 * site's accounts not in the group yet, any number ticked at once; "Someone without an account" shows the
 * email, name and phone fields, needed only then. An address typed there that does belong to an account adds
 * that account.
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
      return $this->buildAddForm($form, $form_state, $group);
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

  /**
   * The add form: site accounts from a list, or someone without an account.
   */
  protected function buildAddForm(array $form, FormStateInterface $form_state, array $group): array {
    try {
      $candidates = $this->manager->listGroupCandidates((int) $group['id']);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      $candidates = [];
    }
    $options = [];
    foreach ($candidates as $account) {
      $options[(int) $account['id']] = ($account['name'] !== '' ? $account['name'] . ' (' . $account['email'] . ')' : $account['email'])
        . ($account['confirmed'] ? '' : ' — ' . $this->t('has not confirmed their address yet'));
    }
    $whoIs = fn (string $who) => ['visible' => [':input[name="who"]' => ['value' => $who]]];

    $form['intro'] = [
      '#type' => 'html_tag',
      '#tag' => 'p',
      '#value' => $this->t('Adding to “@group”. People with an account get your messages the way they chose on My account (email, text or both). Someone without an account gets email only.', ['@group' => $group['name']]),
    ];
    $form['who'] = [
      '#type' => 'radios',
      '#title' => $this->t('Who to add'),
      '#options' => [
        'accounts' => $this->t('People with an account on the site'),
        'contact' => $this->t('Someone without an account'),
      ],
      '#default_value' => $options ? 'accounts' : 'contact',
      '#required' => TRUE,
    ];
    $form['accounts'] = [
      '#type' => 'checkboxes',
      '#title' => $this->t('Tick everyone to add'),
      '#options' => $options,
      '#description' => $options ? $this->t('Everyone with an account who is not in the group yet, by name.') : $this->t('Everyone with an account is in the group already.'),
      '#prefix' => '<div class="group-candidates" style="max-height: 26em; overflow: auto; border: 1px solid #d3d4d9; border-radius: 4px; padding: 0 1em;">',
      '#suffix' => '</div>',
      '#states' => $whoIs('accounts'),
    ];
    $form['contact'] = [
      '#type' => 'container',
      '#states' => $whoIs('contact'),
    ];
    $form['contact']['email'] = [
      '#type' => 'email',
      '#title' => $this->t('Email address'),
      '#states' => ['required' => [':input[name="who"]' => ['value' => 'contact']]],
    ];
    $form['contact']['name'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Name'),
      '#maxlength' => 200,
      '#states' => ['required' => [':input[name="who"]' => ['value' => 'contact']]],
    ];
    $form['contact']['phone'] = [
      '#type' => 'tel',
      '#title' => $this->t('Phone (optional, for your reference)'),
      '#maxlength' => 40,
      '#description' => $this->t('Someone without an account is never texted: texts go only to site accounts whose owners asked for them.'),
    ];
    $form['actions'] = ['#type' => 'actions'];
    $form['actions']['submit'] = ['#type' => 'submit', '#value' => $this->t('Add')];
    $form['actions']['another'] = [
      '#type' => 'submit',
      '#value' => $this->t('Add and add another'),
      '#submit' => ['::submitAndAnother'],
      '#states' => $whoIs('contact'),
    ];
    $form['actions']['cancel'] = [
      '#type' => 'link',
      '#title' => $this->t('Cancel'),
      '#url' => Url::fromRoute('bible_admin.group', ['group_id' => $group['id']]),
      '#attributes' => ['class' => ['button']],
    ];
    return $form;
  }

  public function validateForm(array &$form, FormStateInterface $form_state): void {
    if ($form_state->get('member_id') !== NULL) {
      return;
    }
    if ($form_state->getValue('who') === 'accounts') {
      if (!array_filter((array) $form_state->getValue('accounts'))) {
        $form_state->setErrorByName('accounts', $this->t('Tick at least one person to add.'));
      }
      return;
    }
    if (trim((string) $form_state->getValue('email')) === '') {
      $form_state->setErrorByName('email', $this->t('The email address is needed.'));
    }
    if (trim((string) $form_state->getValue('name')) === '') {
      $form_state->setErrorByName('name', $this->t('The name is needed.'));
    }
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
    if ($form_state->get('member_id') === NULL && $form_state->getValue('who') === 'accounts') {
      $groupId = (int) $form_state->get('group_id');
      try {
        $members = $this->manager->addGroupAccounts($groupId, array_keys(array_filter((array) $form_state->getValue('accounts'))));
      }
      catch (BibleManagerException $exception) {
        $this->messenger()->addError($exception->getMessage());
        $form_state->setRebuild();
        return;
      }
      $this->messenger()->addStatus($this->formatPlural(count($members), 'Added @names.', 'Added @count people: @names.', [
        '@names' => implode(', ', array_map(fn ($member) => $member['name'] ?: $member['email'], $members)),
      ]));
      $form_state->setRedirect('bible_admin.group', ['group_id' => $groupId]);
      return;
    }
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
