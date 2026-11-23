<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Form;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\bible_admin\GroupEditor;
use Drupal\bible_admin\SignatureTaskOwners;
use Drupal\Core\Form\FormBase;
use Drupal\Core\Form\FormStateInterface;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * Adds a signature (belonging to the user adding it) or changes one: a name and the formatted words, in the same
 * editor as the group emails (GroupEditor), since a signature goes at the foot of emails.
 */
class SignatureForm extends FormBase {

  public function __construct(protected BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_signature';
  }

  public function buildForm(array $form, FormStateInterface $form_state, ?string $signature_id = NULL): array {
    $form['#cache'] = ['max-age' => 0];
    $signature = NULL;
    if ($signature_id !== NULL) {
      try {
        $signature = $this->manager->getSignature((int) $signature_id);
      }
      catch (BibleManagerException $exception) {
        $this->messenger()->addError($exception->getMessage());
        return ['back' => ['#type' => 'link', '#title' => $this->t('Back to the signatures'), '#url' => Url::fromRoute('bible_admin.signatures')]];
      }
      $form_state->set('signature_id', (int) $signature['id']);
    }
    $form['name'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Name'),
      '#default_value' => $signature['name'] ?? '',
      '#maxlength' => 200,
      '#required' => TRUE,
      '#description' => $this->t('For you to tell your signatures apart, such as “Celebrate Recovery leader”. It is not part of the signature.'),
    ];
    $form['signature'] = GroupEditor::field((string) $this->t('Signature'), (string) ($signature['html'] ?? ''), 6, TRUE);
    // An administrator chooses whose it is (2026-11-23): a signature or task is only ever used with its owner's.
    if ($this->currentUser()->hasPermission('administer signatures and tasks')) {
      $currentOwner = (int) ($signature['owner_uid'] ?? $this->currentUser()->id());
      $form['owner_uid'] = [
        '#type' => 'select',
        '#title' => $this->t('Owner'),
        '#options' => SignatureTaskOwners::options($currentOwner),
        '#default_value' => $currentOwner,
        '#required' => TRUE,
        '#description' => $this->t('Whose signature this is. Only its owner’s tasks and groups can use it; moving it takes it off the old owner’s tasks and scheduled emails.'),
      ];
    }
    $form['actions'] = ['#type' => 'actions'];
    $form['actions']['submit'] = ['#type' => 'submit', '#value' => $signature === NULL ? $this->t('Add the signature') : $this->t('Save')];
    $form['actions']['cancel'] = [
      '#type' => 'link',
      '#title' => $this->t('Cancel'),
      '#url' => Url::fromRoute('bible_admin.signatures'),
      '#attributes' => ['class' => ['button']],
    ];
    return $form;
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    $signatureId = $form_state->get('signature_id');
    try {
      $signature = $this->manager->saveSignature(
        $signatureId === NULL ? NULL : (int) $signatureId,
        (string) $form_state->getValue('name'),
        GroupEditor::value($form_state->getValue('signature')),
        $form_state->getValue('owner_uid') ? (int) $form_state->getValue('owner_uid') : NULL,
      );
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      $form_state->setRebuild();
      return;
    }
    $this->messenger()->addStatus($signatureId === NULL
      ? $this->t('Added the signature “@name”.', ['@name' => $signature['name']])
      : $this->t('Saved “@name”.', ['@name' => $signature['name']]));
    $form_state->setRedirect('bible_admin.signatures');
  }

}
