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
 * Asks before replacing the site's own FAQ list with the one built into the site.
 */
class FaqBuiltInForm extends ConfirmFormBase {

  public function __construct(private readonly BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_faq_built_in';
  }

  public function getQuestion() {
    return $this->t('Go back to the built-in FAQ questions?');
  }

  public function getDescription() {
    return $this->t('This site’s own questions and the words about the site are deleted, and the FAQ shows the questions built into Bible and Beyond. Notes on questions that are not among those stay on the FAQ notes page, not shown. This cannot be undone.');
  }

  public function getConfirmText() {
    return $this->t('Go back to the built-in questions');
  }

  public function getCancelUrl(): Url {
    return Url::fromRoute('bible_admin.faq_questions');
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    try {
      $this->manager->useBuiltInFaqQuestions();
      $this->messenger()->addStatus($this->t('The FAQ shows the built-in questions again.'));
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
    }
    $form_state->setRedirect('bible_admin.faq_questions');
  }

}
