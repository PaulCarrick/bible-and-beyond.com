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
 * Asks before taking a question off the FAQ.
 */
class DeleteFaqQuestionForm extends ConfirmFormBase {

  private ?array $entry = NULL;

  public function __construct(private readonly BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_delete_faq_question';
  }

  public function buildForm(array $form, FormStateInterface $form_state, ?string $question_id = NULL): array {
    try {
      $this->entry = $this->manager->getFaqQuestion((int) $question_id);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return ['back' => ['#type' => 'link', '#title' => $this->t('Back to the FAQ questions'), '#url' => $this->getCancelUrl()]];
    }
    $form_state->set('question_id', (int) $this->entry['id']);
    $form = parent::buildForm($form, $form_state);
    $form['#cache'] = ['max-age' => 0];
    return $form;
  }

  public function getQuestion() {
    return $this->t('Take “@question” off the FAQ?', ['@question' => $this->entry['question'] ?? '']);
  }

  public function getDescription() {
    return $this->t('Visitors can no longer choose it. Its note stays on the FAQ notes page (not shown) until you move it to another question or delete it.');
  }

  public function getConfirmText() {
    return $this->t('Delete');
  }

  public function getCancelUrl(): Url {
    return Url::fromRoute('bible_admin.faq_questions');
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    try {
      $deleted = $this->manager->deleteFaqQuestion((int) $form_state->get('question_id'));
      $this->messenger()->addStatus($this->t('Deleted “@question”.', ['@question' => $deleted['question']]));
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
    }
    $form_state->setRedirect('bible_admin.faq_questions');
  }

}
