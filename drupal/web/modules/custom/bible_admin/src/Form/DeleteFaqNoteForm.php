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
 * Asks before deleting a note from the site owner under a FAQ answer.
 */
class DeleteFaqNoteForm extends ConfirmFormBase {

  private ?array $note = NULL;

  public function __construct(private readonly BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_delete_faq_note';
  }

  public function buildForm(array $form, FormStateInterface $form_state, ?int $note_id = NULL): array {
    try {
      $this->note = $this->manager->getFaqNote((int) $note_id);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return ['back' => ['#type' => 'link', '#title' => $this->t('Back to the FAQ notes'), '#url' => $this->getCancelUrl()]];
    }
    $form_state->set('note_id', (int) $this->note['id']);
    $form = parent::buildForm($form, $form_state);
    $form['#cache'] = ['max-age' => 0];
    return $form;
  }

  public function getQuestion() {
    return $this->t('Delete the note on “@question”?', ['@question' => $this->note['question'] ?? '']);
  }

  public function getDescription() {
    return $this->t('The note is taken off the FAQ page and its text is deleted. This cannot be undone, so copy the text first if you may want it again.');
  }

  public function getConfirmText() {
    return $this->t('Delete');
  }

  public function getCancelUrl(): Url {
    return Url::fromRoute('bible_admin.faq_notes');
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    try {
      $note = $this->manager->deleteFaqNote((int) $form_state->get('note_id'));
      $this->messenger()->addStatus($this->t('Deleted the note on “@question”.', ['@question' => $note['question']]));
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
    }
    $form_state->setRedirect('bible_admin.faq_notes');
  }

}
