<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Form;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\Core\Form\FormBase;
use Drupal\Core\Form\FormStateInterface;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * Numbers an administrator can change for the links under each verse on the public search page.
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
    $limits = $current['limits'];
    $form_state->set('limits', $limits);

    $form['intro'] = [
      '#type' => 'html_tag',
      '#tag' => 'p',
      '#value' => $this->t('On the search page, each verse in the results has links that open a window. These numbers control two of them. Changes apply to the public site straight away.'),
    ];

    $form['context'] = [
      '#type' => 'fieldset',
      '#title' => $this->t('Show in Context'),
      '#description' => $this->t('Shows the verse in the middle with this many verses around it, in reading order. The window stops at the start and end of the book.'),
    ];
    foreach (self::fields() as $key => $label) {
      $group = $key === 'related_verses_limit' ? 'related' : 'context';
      if ($group === 'related' && !isset($form['related'])) {
        $form['related'] = [
          '#type' => 'fieldset',
          '#title' => $this->t('Related Verses'),
          '#description' => $this->t('Lists the verses that readers have cross-referenced with the chosen verse, best-voted first. Showing more is slower to read.'),
        ];
      }
      $form[$group][$key] = [
        '#type' => 'number',
        '#title' => $label,
        '#description' => $this->t('From @min to @max.', ['@min' => $limits[$key]['min'], '@max' => $limits[$key]['max']]),
        '#default_value' => $current['settings'][$key],
        '#min' => $limits[$key]['min'],
        '#max' => $limits[$key]['max'],
        '#step' => 1,
        '#required' => TRUE,
      ];
    }

    $form['actions'] = ['#type' => 'actions'];
    $form['actions']['submit'] = [
      '#type' => 'submit',
      '#value' => $this->t('Save'),
      '#button_type' => 'primary',
    ];
    return $form;
  }

  /**
   * The settings on this page and what each is called.
   */
  private static function fields(): array {
    return [
      'context_verses_before' => t('Verses before'),
      'context_verses_after' => t('Verses after'),
      'related_verses_limit' => t('Related verses to show'),
    ];
  }

  public function validateForm(array &$form, FormStateInterface $form_state): void {
    $limits = $form_state->get('limits');
    foreach (self::fields() as $key => $label) {
      $value = $form_state->getValue($key);
      $min = (int) $limits[$key]['min'];
      $max = (int) $limits[$key]['max'];
      if (!is_numeric($value) || (string) (int) $value !== trim((string) $value) || (int) $value < $min || (int) $value > $max) {
        $form_state->setErrorByName($key, $this->t('@label must be a whole number from @min to @max.', ['@label' => $label, '@min' => $min, '@max' => $max]));
      }
    }
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    try {
      $this->manager->saveSearchSettings(
        (int) $form_state->getValue('context_verses_before'),
        (int) $form_state->getValue('context_verses_after'),
        (int) $form_state->getValue('related_verses_limit'),
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
