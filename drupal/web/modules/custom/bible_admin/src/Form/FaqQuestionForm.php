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
 * Adds a FAQ question or changes one: its heading (one of the list's, or a new one) and its wording.
 */
class FaqQuestionForm extends FormBase {

  private const NEW_HEADING = '_new';

  public function __construct(protected BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_faq_question';
  }

  public function buildForm(array $form, FormStateInterface $form_state, ?string $question_id = NULL): array {
    $form['#cache'] = ['max-age' => 0];
    $back = Url::fromRoute('bible_admin.faq_questions');
    try {
      $list = $this->manager->getFaqQuestionList();
      $entry = $question_id === NULL ? NULL : $this->manager->getFaqQuestion((int) $question_id);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return ['back' => ['#type' => 'link', '#title' => $this->t('Back to the FAQ questions'), '#url' => $back]];
    }
    if ($entry !== NULL) {
      $form_state->set('question_id', (int) $entry['id']);
    }
    $headings = [];
    foreach ($list['groups'] as $group) {
      $headings[$group['heading']] = $group['heading'];
    }
    $form['heading'] = [
      '#type' => 'select',
      '#title' => $this->t('Heading'),
      '#options' => $headings + [self::NEW_HEADING => $this->t('A new heading…')],
      '#default_value' => $entry['heading'] ?? array_key_last($headings),
      '#required' => TRUE,
      '#description' => $this->t('The questions are grouped under their headings on the FAQ page. A question moved to another heading goes last in it.'),
    ];
    $form['new_heading'] = [
      '#type' => 'textfield',
      '#title' => $this->t('New heading'),
      '#maxlength' => 200,
      '#states' => ['visible' => [':input[name="heading"]' => ['value' => self::NEW_HEADING]]],
      '#description' => $this->t('It goes after the other headings.'),
    ];
    $form['question'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Question'),
      '#default_value' => $entry['question'] ?? '',
      '#maxlength' => 300,
      '#required' => TRUE,
      '#description' => $entry === NULL
        ? $this->t('As visitors will see it, such as “What is Celebrate Recovery?”. The AI answers it the first time someone opens it.')
        : $this->t('Rewording it gets a new answer from the AI the next time someone opens it; its note moves with it.'),
    ];
    $form['actions'] = ['#type' => 'actions'];
    $form['actions']['submit'] = ['#type' => 'submit', '#value' => $entry === NULL ? $this->t('Add the question') : $this->t('Save')];
    $form['actions']['cancel'] = ['#type' => 'link', '#title' => $this->t('Cancel'), '#url' => $back, '#attributes' => ['class' => ['button']]];
    return $form;
  }

  public function validateForm(array &$form, FormStateInterface $form_state): void {
    if ($form_state->getValue('heading') === self::NEW_HEADING && trim((string) $form_state->getValue('new_heading')) === '') {
      $form_state->setErrorByName('new_heading', $this->t('Give the new heading.'));
    }
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    $questionId = $form_state->get('question_id');
    $heading = (string) $form_state->getValue('heading');
    if ($heading === self::NEW_HEADING) {
      $heading = trim((string) $form_state->getValue('new_heading'));
    }
    try {
      $saved = $this->manager->saveFaqQuestion($questionId === NULL ? NULL : (int) $questionId, $heading, (string) $form_state->getValue('question'));
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      $form_state->setRebuild();
      return;
    }
    $this->messenger()->addStatus($questionId === NULL
      ? $this->t('Added “@question”.', ['@question' => $saved['question']])
      : $this->t('Saved “@question”.', ['@question' => $saved['question']]));
    $form_state->setRedirect('bible_admin.faq_questions');
  }

}
