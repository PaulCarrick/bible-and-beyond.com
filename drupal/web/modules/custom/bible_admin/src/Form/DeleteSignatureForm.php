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
 * Asks before deleting a signature.
 */
class DeleteSignatureForm extends ConfirmFormBase {

  private ?array $signature = NULL;

  public function __construct(private readonly BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_delete_signature';
  }

  public function buildForm(array $form, FormStateInterface $form_state, ?string $signature_id = NULL): array {
    try {
      $this->signature = $this->manager->getSignature((int) $signature_id);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return ['back' => ['#type' => 'link', '#title' => $this->t('Back to the signatures'), '#url' => $this->getCancelUrl()]];
    }
    $form_state->set('signature_id', (int) $this->signature['id']);
    $form = parent::buildForm($form, $form_state);
    $form['#cache'] = ['max-age' => 0];
    return $form;
  }

  public function getQuestion() {
    return $this->t('Delete the signature “@name”?', ['@name' => $this->signature['name'] ?? '']);
  }

  public function getDescription() {
    return $this->t('This cannot be undone.');
  }

  public function getConfirmText() {
    return $this->t('Delete');
  }

  public function getCancelUrl(): Url {
    return Url::fromRoute('bible_admin.signatures');
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    try {
      $signature = $this->manager->deleteSignature((int) $form_state->get('signature_id'));
      $this->messenger()->addStatus($this->t('Deleted the signature “@name”.', ['@name' => $signature['name']]));
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
    }
    $form_state->setRedirect('bible_admin.signatures');
  }

}
