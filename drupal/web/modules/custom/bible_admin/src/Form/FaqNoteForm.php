<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Form;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\Core\Form\FormBase;
use Drupal\Core\Form\FormStateInterface;
use Drupal\Core\Url;
use Drupal\filter\Entity\FilterFormat;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * Adds a note from the site owner under one FAQ answer, or changes one.
 *
 * The note is written in CKEditor (the "FAQ note" text format) and sent to the Python tool, which cleans it
 * with the public site's allowlist and stores it in the Bible database. Drupal itself never displays it.
 */
class FaqNoteForm extends FormBase {

  private const FORMAT = 'faq_note';

  public function __construct(protected BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_faq_note';
  }

  public function buildForm(array $form, FormStateInterface $form_state, ?int $note_id = NULL): array {
    $form['#cache'] = ['max-age' => 0];
    $back = ['#type' => 'link', '#title' => $this->t('Back to the FAQ notes'), '#url' => Url::fromRoute('bible_admin.faq_notes')];
    try {
      $note = $note_id === NULL ? NULL : $this->manager->getFaqNote((int) $note_id);
      $groups = $this->manager->listFaqQuestions();
      $notes = $this->manager->listFaqNotes();
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return ['back' => $back];
    }
    if ($note !== NULL) {
      $form_state->set('note_id', (int) $note['id']);
    }

    // One note per question: the questions that have one are left out, except this note's own.
    $taken = [];
    foreach ($notes as $other) {
      if ($note === NULL || $other['id'] !== $note['id']) {
        $taken[$other['question']] = TRUE;
      }
    }
    $options = [];
    foreach ($groups as $group) {
      foreach ($group['questions'] as $entry) {
        if (!isset($taken[$entry['question']])) {
          $options[$group['heading']][$entry['question']] = $entry['question'];
        }
      }
    }
    if ($note !== NULL && !$note['is_listed']) {
      $options[(string) $this->t('No longer on the FAQ (the note is not shown)')][$note['question']] = $note['question'];
    }
    if (!$options) {
      $this->messenger()->addWarning($this->t('Every FAQ question has a note already. Edit one of them instead.'));
      return ['back' => $back];
    }

    $form['question'] = [
      '#type' => 'select',
      '#title' => $this->t('Question'),
      '#options' => $options,
      '#default_value' => $note['question'] ?? NULL,
      '#empty_option' => $this->t('- Choose a question -'),
      '#required' => TRUE,
      '#description' => $note === NULL ? $this->t('Questions that already have a note are not listed.') : '',
    ];

    $format = FilterFormat::load(self::FORMAT);
    $description = $this->t('Shown in a box headed “A note from the site owner”, under the AI’s answer. The editor’s formatting is kept: headings, bold, italic, underline, superscript (verse numbers), links, lists and quotations. Pictures, colours and fonts are not. Links that work: other websites and links to this site, such as a verse (copy the address of a verse in the Bible reader, like https://bible-and-beyond.com/?read=BSB&amp;book=43&amp;chapter=3&amp;verse=16), another FAQ answer (https://bible-and-beyond.com/faq?question= followed by the question) or a page (https://bible-and-beyond.com/search). Links to a verse and to other websites open in a new tab.');
    if ($format && $format->access('use')) {
      $form['note'] = [
        '#type' => 'text_format',
        '#title' => $this->t('Note'),
        '#format' => self::FORMAT,
        '#allowed_formats' => [self::FORMAT],
        '#default_value' => $note['html'] ?? '',
        '#rows' => 20,
        '#required' => TRUE,
        '#description' => $description,
        '#after_build' => [[static::class, 'hideFormatHelp']],
      ];
    }
    else {
      // Without the editor (CKEditor 5 not enabled here), the note is written as HTML.
      $form['note'] = [
        '#type' => 'textarea',
        '#title' => $this->t('Note (HTML)'),
        '#default_value' => $note['html'] ?? '',
        '#rows' => 20,
        '#required' => TRUE,
        '#description' => $description,
      ];
    }

    $form['actions'] = ['#type' => 'actions'];
    $form['actions']['submit'] = ['#type' => 'submit', '#value' => $note === NULL ? $this->t('Add the note') : $this->t('Save')];
    $form['actions']['cancel'] = ['#type' => 'link', '#title' => $this->t('Cancel'), '#url' => Url::fromRoute('bible_admin.faq_notes')];
    return $form;
  }

  /**
   * Takes away the "About text formats" link and the format's guidelines: there is only the one format.
   */
  public static function hideFormatHelp(array $element): array {
    unset($element['format']['help'], $element['format']['guidelines']);
    return $element;
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    $noteId = $form_state->get('note_id');
    $question = (string) $form_state->getValue('question');
    $value = $form_state->getValue('note');
    $html = is_array($value) ? (string) ($value['value'] ?? '') : (string) $value;
    try {
      if ($noteId === NULL) {
        $note = $this->manager->createFaqNote($question, $html);
        $this->messenger()->addStatus($this->t('Added the note on “@question”.', ['@question' => $note['question']]));
      }
      else {
        $note = $this->manager->updateFaqNote((int) $noteId, $question, $html);
        $this->messenger()->addStatus($this->t('Saved the note on “@question”.', ['@question' => $note['question']]));
      }
    }
    catch (BibleManagerException $exception) {
      // Stay on the form, with what was written, so it can be corrected.
      $this->messenger()->addError($exception->getMessage());
      $form_state->setRebuild();
      return;
    }
    $form_state->setRedirect('bible_admin.faq_notes');
  }

}
