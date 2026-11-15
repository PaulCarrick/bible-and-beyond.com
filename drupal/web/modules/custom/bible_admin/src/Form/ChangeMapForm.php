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
 * Asks before publishing, hiding or deleting a map.
 */
class ChangeMapForm extends ConfirmFormBase {

  private ?array $map = NULL;

  private string $action = '';

  public function __construct(private readonly BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_change_map';
  }

  public function buildForm(array $form, FormStateInterface $form_state, string $action = '', string $map_id = ''): array {
    $this->action = $action;
    try {
      $this->map = $this->manager->getMap($map_id);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return ['back' => ['#type' => 'link', '#title' => $this->t('Back to the maps'), '#url' => $this->getCancelUrl()]];
    }
    $form_state->set('action', $action);
    $form_state->set('map_id', $this->map['id']);
    $form = parent::buildForm($form, $form_state);
    $form['#cache'] = ['max-age' => 0];
    return $form;
  }

  public function getQuestion() {
    $title = $this->map['title'] ?? '';
    return match ($this->action) {
      'publish' => $this->t('Publish “@title”?', ['@title' => $title]),
      'unpublish' => $this->t('Hide “@title”?', ['@title' => $title]),
      default => $this->t('Delete “@title”?', ['@title' => $title]),
    };
  }

  public function getDescription() {
    $marks = (int) ($this->map['mark_count'] ?? 0);
    return match ($this->action) {
      'publish' => $this->t('Everyone can then see it on the site. Publish only a map that is in the public domain or that you have permission to publish.'),
      'unpublish' => $this->t('It is taken off the site; its file, details and the members\' notes, pins and routes on it are kept, and you can publish it again.'),
      default => $marks === 0
        ? $this->t('The map and its files are deleted. This cannot be undone; you would have to upload it again.')
        : $this->t('The map and its files are deleted, with @marks. This cannot be undone; you would have to upload it again.', [
          '@marks' => $this->formatPlural($marks, "one member's note, pin or route on it", "the @count notes, pins and routes that members added to it"),
        ]),
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
    return Url::fromRoute('bible_admin.maps');
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    $action = (string) $form_state->get('action');
    try {
      $map = $this->manager->changeMap($action, (string) $form_state->get('map_id'));
      $this->messenger()->addStatus(match ($action) {
        'publish' => $this->t('Published “@title”.', ['@title' => $map['title']]),
        'unpublish' => $this->t('Hid “@title”.', ['@title' => $map['title']]),
        default => $this->t('Deleted “@title”.', ['@title' => $map['title']]),
      });
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
    }
    $form_state->setRedirect('bible_admin.maps');
  }

}
