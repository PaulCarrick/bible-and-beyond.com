<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Form;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\Core\Form\FormBase;
use Drupal\Core\Form\FormStateInterface;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * How many verses "Show in Context" shows around a verse on the public search page.
 */
class SearchSettingsForm extends FormBase {

  public function __construct(private readonly BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_search_settings';
  }

  public function buildForm(array $form, FormStateInterface $form_state): array {
    try {
      $current = $this->manager->getSearchSettings();
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return $form;
    }
    $limit = (int) $current['context_limit'];
    $form_state->set('context_limit', $limit);

    $form['intro'] = [
      '#type' => 'html_tag',
      '#tag' => 'p',
      '#value' => $this->t('On the search page, each verse in the results has a "Show in Context" link. It opens a window with the verse in the middle and these numbers of verses around it, in reading order. The window stops at the start and end of the book. Changes apply to the public site straight away.'),
    ];
    $form['context_verses_before'] = [
      '#type' => 'number',
      '#title' => $this->t('Verses before'),
      '#description' => $this->t('From 0 to @limit.', ['@limit' => $limit]),
      '#default_value' => $current['settings']['context_verses_before'],
      '#min' => 0,
      '#max' => $limit,
      '#step' => 1,
      '#required' => TRUE,
    ];
    $form['context_verses_after'] = [
      '#type' => 'number',
      '#title' => $this->t('Verses after'),
      '#description' => $this->t('From 0 to @limit.', ['@limit' => $limit]),
      '#default_value' => $current['settings']['context_verses_after'],
      '#min' => 0,
      '#max' => $limit,
      '#step' => 1,
      '#required' => TRUE,
    ];

    $form['actions'] = ['#type' => 'actions'];
    $form['actions']['submit'] = [
      '#type' => 'submit',
      '#value' => $this->t('Save'),
      '#button_type' => 'primary',
    ];
    return $form;
  }

  public function validateForm(array &$form, FormStateInterface $form_state): void {
    $limit = (int) $form_state->get('context_limit');
    foreach (['context_verses_before' => $this->t('Verses before'), 'context_verses_after' => $this->t('Verses after')] as $key => $label) {
      $value = $form_state->getValue($key);
      if (!is_numeric($value) || (string) (int) $value !== trim((string) $value) || (int) $value < 0 || (int) $value > $limit) {
        $form_state->setErrorByName($key, $this->t('@label must be a whole number from 0 to @limit.', ['@label' => $label, '@limit' => $limit]));
      }
    }
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    try {
      $this->manager->saveSearchSettings(
        (int) $form_state->getValue('context_verses_before'),
        (int) $form_state->getValue('context_verses_after'),
      );
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      $form_state->setRebuild();
      return;
    }
    $this->messenger()->addStatus($this->t('Saved. The search page uses the new numbers now.'));
  }

}
