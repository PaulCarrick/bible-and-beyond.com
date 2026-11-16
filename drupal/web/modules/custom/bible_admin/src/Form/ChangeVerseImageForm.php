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
 * Asks before putting a verse a day picture in use, taking it out of use or deleting it.
 */
class ChangeVerseImageForm extends ConfirmFormBase {

  private ?array $image = NULL;

  private string $action = '';

  public function __construct(private readonly BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_change_verse_image';
  }

  public function buildForm(array $form, FormStateInterface $form_state, string $action = '', string $image_id = ''): array {
    $this->action = $action;
    try {
      $this->image = $this->manager->getVerseImage($image_id);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return ['back' => ['#type' => 'link', '#title' => $this->t('Back to the pictures'), '#url' => $this->getCancelUrl()]];
    }
    $form_state->set('action', $action);
    $form_state->set('image_id', $this->image['id']);
    $form = parent::buildForm($form, $form_state);
    $form['#cache'] = ['max-age' => 0];
    return $form;
  }

  public function getQuestion() {
    $title = $this->image['title'] ?? '';
    return match ($this->action) {
      'use' => $this->t('Put “@title” in use?', ['@title' => $title]),
      'unuse' => $this->t('Take “@title” out of use?', ['@title' => $title]),
      default => $this->t('Delete “@title”?', ['@title' => $title]),
    };
  }

  public function getDescription() {
    return match ($this->action) {
      'use' => $this->t('It can then be chosen as the background of a verse a day picture message.'),
      'unuse' => $this->t('It is kept, but never chosen until you put it in use again.'),
      default => $this->t('The picture and its files are deleted. This cannot be undone; you would have to upload it again.'),
    };
  }

  public function getConfirmText() {
    return match ($this->action) {
      'use' => $this->t('Put in use'),
      'unuse' => $this->t('Take out of use'),
      default => $this->t('Delete'),
    };
  }

  public function getCancelUrl(): Url {
    return Url::fromRoute('bible_admin.verse_images');
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    $action = (string) $form_state->get('action');
    try {
      $image = $this->manager->changeVerseImage($action, (string) $form_state->get('image_id'));
      $this->messenger()->addStatus(match ($action) {
        'use' => $this->t('“@title” is in use.', ['@title' => $image['title']]),
        'unuse' => $this->t('“@title” is out of use.', ['@title' => $image['title']]),
        default => $this->t('Deleted “@title”.', ['@title' => $image['title']]),
      });
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
    }
    $form_state->setRedirect('bible_admin.verse_images');
  }

}
