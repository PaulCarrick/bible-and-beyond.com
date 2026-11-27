<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Form;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\bible_admin\GroupEditor;
use Drupal\Core\Form\FormBase;
use Drupal\Core\Form\FormStateInterface;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;
use Symfony\Component\HttpFoundation\Response;

/**
 * Sign-up sheet (added 2026-11-27 at the owner's request): a group's sign-up sheet for a period as a PDF, in the
 * layout of the owner's paper "After Church Fellowship Time" form (signup_sheet.py). The rows are the group's own
 * tasks (the Group chosen on each task) on each date they fall on: blank (each task's expected occurrences) or filled in from the scheduled tasks.
 * The title is the group's Description (else its name); the notes at the foot (the editor; left off when empty) are
 * kept for next time only when Save this note is ticked, for this report and group (report_notes).
 */
class SignUpSheetForm extends FormBase {

  public function __construct(protected BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_sign_up_sheet';
  }

  public function buildForm(array $form, FormStateInterface $form_state): array {
    $form['#cache'] = ['max-age' => 0];
    try {
      $groups = $this->manager->signUpSheetGroups();
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return $form;
    }
    if (!$groups) {
      $form['none'] = [
        '#markup' => '<p>' . $this->t('You have no groups yet. Make one on the <a href=":url">Groups</a> page, then choose it as the Group of its tasks.', [
          ':url' => Url::fromRoute('bible_admin.groups')->toString(),
        ]) . '</p>',
      ];
      return $form;
    }
    $byId = [];
    $options = [];
    $showLeader = count(array_unique(array_column($groups, 'owner_uid'))) > 1;
    foreach ($groups as $group) {
      $byId[(int) $group['id']] = $group;
      $options[(int) $group['id']] = $showLeader && $group['owner_name'] !== ''
        ? $this->t('@group (led by @leader)', ['@group' => $group['name'], '@leader' => $group['owner_name']])
        : $group['name'];
    }
    // The group: the one posted, else the one in the address (?group=, set when the Group list is changed), else the
    // first. Changing the group reloads the page rather than swapping the notes editor by AJAX: an editor swapped in
    // by AJAX did not send what was typed in it (found 2026-11-27, the owner's notes arrived empty).
    $groupId = (int) ($form_state->getValue('group_id') ?? $this->getRequest()->query->get('group') ?? array_key_first($byId));
    if (!isset($byId[$groupId])) {
      $groupId = (int) array_key_first($byId);
    }
    $group = $byId[$groupId];

    $form['intro'] = [
      '#markup' => '<p>' . $this->t('A sign-up sheet to print: one block for each date in the period on which any of the group’s tasks falls (by each task’s own recurrence), with a row for each place to fill. A task is on a group’s sheet when that group is chosen as its Group; set that, how many places it has (Expected occurrences) and its place in the list on the task’s Edit page.') . '</p>',
    ];
    $form['group_id'] = [
      '#type' => 'select',
      '#title' => $this->t('Group'),
      '#options' => $options,
      '#default_value' => $groupId,
      '#required' => TRUE,
      '#attributes' => [
        'onchange' => "window.location.href = window.location.pathname + '?group=' + encodeURIComponent(this.value);",
      ],
      '#description' => $this->t('Choosing another group reloads the page with that group’s title and saved notes.'),
    ];
    $today = new \DateTimeImmutable('today');
    $form['period'] = ['#type' => 'container', '#attributes' => ['class' => ['container-inline']]];
    $form['period']['start'] = [
      '#type' => 'date',
      '#title' => $this->t('From'),
      '#default_value' => $today->format('Y-m-d'),
      '#required' => TRUE,
    ];
    $form['period']['end'] = [
      '#type' => 'date',
      '#title' => $this->t('To'),
      '#default_value' => $today->modify('+1 month -1 day')->format('Y-m-d'),
      '#required' => TRUE,
    ];
    $form['filled'] = [
      '#type' => 'checkbox',
      '#title' => $this->t('Fill in the people scheduled'),
      '#default_value' => TRUE,
      '#description' => $this->t('Ticked: each date lists the people scheduled (with their notes, email and phone), then blank rows up to the number each task expects; someone not confirmed yet is marked so. Unticked: a blank sheet, each task with as many rows as it expects.'),
    ];

    // The title and the notes saved for this group.
    $form['group_box'] = ['#type' => 'container', '#attributes' => ['id' => 'sign-up-sheet-group']];
    $notesKey = 'notes';
    $form_state->set('notes_key', $notesKey);
    // The title is the group's Description (2026-11-27, the owner's request), else its name; set on the group.
    $form['group_box']['title'] = [
      '#type' => 'item',
      '#title' => $this->t('Title'),
      '#markup' => '<p>' . $this->t('@title', ['@title' => $group['title']]) . '</p>',
      '#description' => $this->t('The group’s Description (or its name when it has none). Change it on the group’s <a href=":url">Edit</a> page.', [
        ':url' => Url::fromRoute('bible_admin.group_edit', ['group_id' => $groupId])->toString(),
      ]),
    ];
    $form['group_box'][$notesKey] = GroupEditor::field(
      (string) $this->t('Notes'),
      (string) $group['sheet_notes_html'],
      6,
      FALSE,
      (string) $this->t('Shown at the foot of the sheet with no heading; leave empty for none.'),
    );
    // Saved only when asked (2026-11-27, the owner's request), for this report and group (report_notes).
    $form['group_box']['save_notes'] = [
      '#type' => 'checkbox',
      '#title' => $this->t('Save this note'),
      '#default_value' => FALSE,
      '#description' => $this->t('Ticked: these notes come up again next time you make this group’s sign-up sheet (an empty note clears the saved one). Unticked: they go on this PDF only. Other reports are not affected.'),
    ];

    $form['actions'] = ['#type' => 'actions'];
    $form['actions']['submit'] = ['#type' => 'submit', '#value' => $this->t('Make the PDF')];
    $form['actions']['cancel'] = [
      '#type' => 'link',
      '#title' => $this->t('Back to the scheduled tasks'),
      '#url' => Url::fromRoute('bible_admin.scheduled_tasks'),
      '#attributes' => ['class' => ['button']],
    ];
    return $form;
  }

  public function validateForm(array &$form, FormStateInterface $form_state): void {
    if ((string) $form_state->getValue('end') < (string) $form_state->getValue('start')) {
      $form_state->setErrorByName('end', $this->t('The last date comes before the first.'));
    }
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    $notesKey = (string) $form_state->get('notes_key');
    try {
      $sheet = $this->manager->makeSignUpSheet([
        'group_id' => (int) $form_state->getValue('group_id'),
        'start' => (string) $form_state->getValue('start'),
        'end' => (string) $form_state->getValue('end'),
        'filled' => (bool) $form_state->getValue('filled'),
        'notes' => GroupEditor::value($form_state->getValue($notesKey)),
        'save_notes' => (bool) $form_state->getValue('save_notes'),
      ]);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      $form_state->setRebuild();
      return;
    }
    $pdf = base64_decode((string) $sheet['pdf'], TRUE);
    if ($pdf === FALSE) {
      $this->messenger()->addError($this->t('The sheet could not be made.'));
      $form_state->setRebuild();
      return;
    }
    $name = str_replace(['"', '\\'], '', (string) $sheet['file_name']);
    $response = new Response($pdf, 200, [
      'Content-Type' => 'application/pdf',
      'Content-Disposition' => 'attachment; filename="' . $name . '"; filename*=UTF-8\'\'' . rawurlencode($name),
      'Cache-Control' => 'private, no-store',
    ]);
    $form_state->setResponse($response);
  }

}
