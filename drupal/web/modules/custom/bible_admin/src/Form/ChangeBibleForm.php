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
 * Asks for confirmation before publishing, hiding or deleting a Bible.
 */
class ChangeBibleForm extends ConfirmFormBase {

  private string $action = '';

  private string $code = '';

  public function __construct(private readonly BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_change';
  }

  public function buildForm(array $form, FormStateInterface $form_state, string $action = '', string $code = ''): array {
    $this->action = $action;
    $this->code = $code;
    $form = parent::buildForm($form, $form_state);

    if ($this->action === 'delete') {
      $form['confirm_code'] = [
        '#type' => 'textfield',
        '#title' => $this->t('Type @code to confirm', ['@code' => $this->code]),
        '#required' => TRUE,
        '#size' => 12,
      ];
    }
    return $form;
  }

  public function getQuestion() {
    return match ($this->action) {
      'publish' => $this->t('Publish @code?', ['@code' => $this->code]),
      'unpublish' => $this->t('Hide @code from search?', ['@code' => $this->code]),
      default => $this->t('Delete @code?', ['@code' => $this->code]),
    };
  }

  public function getDescription() {
    return match ($this->action) {
      'publish' => $this->t('Visitors will be able to search this Bible, and it will appear in the Bible list on the search page.'),
      'unpublish' => $this->t('The Bible disappears from the search page and from search results. Its text stays in the database, and you can publish it again.'),
      default => $this->t('This permanently removes the Bible and all of its verses from the search database. To get it back you would have to upload the file again.'),
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
    return Url::fromRoute('bible_admin.list');
  }

  public function validateForm(array &$form, FormStateInterface $form_state): void {
    if ($this->action === 'delete' && strtoupper(trim((string) $form_state->getValue('confirm_code'))) !== $this->code) {
      $form_state->setErrorByName('confirm_code', $this->t('Type the code exactly as shown to confirm.'));
    }
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    try {
      if ($this->action === 'delete') {
        $result = $this->manager->delete($this->code);
        $this->messenger()->addStatus($this->t('Deleted @code and its @count verses.', [
          '@code' => $this->code,
          '@count' => number_format((int) $result['deleted_verse_count']),
        ]));
      }
      else {
        $this->manager->setPublished($this->code, $this->action === 'publish');
        $this->messenger()->addStatus($this->action === 'publish'
          ? $this->t('@code is now published.', ['@code' => $this->code])
          : $this->t('@code is now hidden.', ['@code' => $this->code]));
      }
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
    }
    $form_state->setRedirect('bible_admin.list');
  }

}
