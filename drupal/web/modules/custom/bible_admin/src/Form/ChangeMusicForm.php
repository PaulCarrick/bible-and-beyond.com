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
 * Asks before publishing, hiding or deleting a song of the Christian music section.
 */
class ChangeMusicForm extends ConfirmFormBase {

  private ?array $song = NULL;

  private string $action = '';

  public function __construct(private readonly BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_change_music';
  }

  public function buildForm(array $form, FormStateInterface $form_state, string $action = '', string $song_id = ''): array {
    $this->action = $action;
    try {
      $this->song = $this->manager->getMusic($song_id);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return ['back' => ['#type' => 'link', '#title' => $this->t('Back to the songs'), '#url' => $this->getCancelUrl()]];
    }
    $form_state->set('action', $action);
    $form_state->set('song_id', $this->song['id']);
    $form = parent::buildForm($form, $form_state);
    $form['#cache'] = ['max-age' => 0];
    return $form;
  }

  public function getQuestion() {
    $title = $this->song['title'] ?? '';
    return match ($this->action) {
      'publish' => $this->t('Publish “@title”?', ['@title' => $title]),
      'unpublish' => $this->t('Hide “@title”?', ['@title' => $title]),
      default => $this->t('Delete “@title”?', ['@title' => $title]),
    };
  }

  public function getDescription() {
    return match ($this->action) {
      'publish' => $this->t('Everyone can then play it and read its words on the site. Publish only a recording that is in the public domain or that you have permission to publish.'),
      'unpublish' => $this->t('It is taken off the site; its file and details are kept, and you can publish it again.'),
      default => $this->t('The song and its file are deleted. This cannot be undone; you would have to upload it again.'),
    };
  }

  public function getConfirmText() {
    return match ($this->action) {
      'publish' => $this->t('Publish'),
      'unpublish' => $this->t('Hide'),
      default => $this->t('Delete'),
    };
  }

  public function getCancelUrl(): Url {
    return Url::fromRoute('bible_admin.music');
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    $action = (string) $form_state->get('action');
    try {
      $song = $this->manager->changeMusic($action, (string) $form_state->get('song_id'));
      $this->messenger()->addStatus(match ($action) {
        'publish' => $this->t('Published “@title”.', ['@title' => $song['title']]),
        'unpublish' => $this->t('Hid “@title”.', ['@title' => $song['title']]),
        default => $this->t('Deleted “@title”.', ['@title' => $song['title']]),
      });
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
    }
    $form_state->setRedirect('bible_admin.music');
  }

}
