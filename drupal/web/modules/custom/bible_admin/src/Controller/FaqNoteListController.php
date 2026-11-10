<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Controller;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\Core\Controller\ControllerBase;
use Drupal\Core\Datetime\DateFormatterInterface;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * The list of the site owner's notes under the FAQ answers, with Edit and Delete for each.
 */
class FaqNoteListController extends ControllerBase {

  public function __construct(
    private readonly BibleManager $manager,
    private readonly DateFormatterInterface $dateFormatter,
  ) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'), $container->get('date.formatter'));
  }

  public function build(): array {
    $build = [
      '#cache' => ['max-age' => 0],
      'intro' => [
        '#type' => 'html_tag',
        '#tag' => 'p',
        '#value' => $this->t('A note is shown in a box headed “A note from the site owner”, under the AI’s answer to its question on the FAQ page. A question can have one note. Changes show on the site at once (a page already open shows them after a reload).'),
      ],
    ];

    try {
      $notes = $this->manager->listFaqNotes();
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return $build;
    }

    $rows = [];
    foreach ($notes as $note) {
      $links = [
        ['title' => $this->t('Edit'), 'url' => Url::fromRoute('bible_admin.faq_note_edit', ['note_id' => $note['id']])],
        ['title' => $this->t('Delete'), 'url' => Url::fromRoute('bible_admin.faq_note_delete', ['note_id' => $note['id']])],
      ];
      $question = $note['is_listed']
        ? ['#plain_text' => $note['question']]
        : [
          '#markup' => $this->t('@question <strong>(no longer on the FAQ, so not shown; edit the note to move it to another question)</strong>', ['@question' => $note['question']]),
        ];
      $rows[] = [
        ['data' => $question],
        ['data' => ['#plain_text' => $note['preview']]],
        ['data' => ['#plain_text' => $this->formatDate($note['updated_at'])]],
        ['data' => ['#type' => 'operations', '#links' => $links]],
      ];
    }

    $build['table'] = [
      '#type' => 'table',
      '#header' => [$this->t('Question'), $this->t('Beginning of the note'), $this->t('Last changed'), $this->t('Operations')],
      '#rows' => $rows,
      '#empty' => $this->t('There are no notes yet.'),
    ];
    return $build;
  }

  private function formatDate(string $iso): string {
    $time = strtotime($iso);
    return $time === FALSE ? '' : $this->dateFormatter->format($time, 'short');
  }

}
