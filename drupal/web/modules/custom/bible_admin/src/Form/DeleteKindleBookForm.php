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
 * Asks before deleting a Kindle book (its link and picture here; nothing changes at Amazon).
 */
class DeleteKindleBookForm extends ConfirmFormBase {

  private ?array $book = NULL;

  private string $collection = 'books';

  public function __construct(private readonly BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_delete_kindle_book';
  }

  public function buildForm(array $form, FormStateInterface $form_state, string $collection = 'books', ?string $book_id = NULL): array {
    $this->collection = $collection;
    try {
      $this->book = $this->manager->getKindleBook((int) $book_id);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return ['back' => ['#type' => 'link', '#title' => $this->t('Back'), '#url' => $this->getCancelUrl()]];
    }
    $form_state->set('book_id', (int) $this->book['id']);
    $form_state->set('collection', $collection);
    $form = parent::buildForm($form, $form_state);
    $form['#cache'] = ['max-age' => 0];
    return $form;
  }

  public function getQuestion() {
    return $this->t('Delete the Kindle book “@title”?', ['@title' => $this->book['title'] ?? '']);
  }

  public function getDescription() {
    return $this->t('Its link and picture are deleted from this site. Nothing changes in anyone’s Kindle library.');
  }

  public function getConfirmText() {
    return $this->t('Delete');
  }

  public function getCancelUrl(): Url {
    return Url::fromRoute('bible_admin.library', ['collection' => $this->collection]);
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    try {
      $book = $this->manager->deleteKindleBook((int) $form_state->get('book_id'));
      $this->messenger()->addStatus($this->t('Deleted “@title”.', ['@title' => $book['title']]));
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
    }
    $form_state->setRedirect('bible_admin.library', ['collection' => (string) $form_state->get('collection')]);
  }

}
