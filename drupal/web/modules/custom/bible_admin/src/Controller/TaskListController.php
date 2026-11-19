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
 * The tasks this user may see (their own, or everyone's with an Owner column): how often each comes round and its
 * next date, with Edit and Delete.
 */
class TaskListController extends ControllerBase {

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
        '#value' => $this->t('A task comes round every week, every two weeks or every month, and has the words of a first and a second notification. Only you see your tasks. (The notifications are not sent yet.) Use Schedule beside a task to give it to a site user on one of its next dates; the Scheduled tasks page lists them.'),
      ],
    ];
    try {
      $tasks = $this->manager->listTasks();
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return $build;
    }
    $showOwner = $this->currentUser()->hasPermission('administer signatures and tasks');

    $rows = [];
    foreach ($tasks as $task) {
      $links = [
        ['title' => $this->t('Schedule'), 'url' => Url::fromRoute('bible_admin.task_schedule', ['task_id' => $task['id']])],
        ['title' => $this->t('Edit'), 'url' => Url::fromRoute('bible_admin.task_edit', ['task_id' => $task['id']])],
        ['title' => $this->t('Delete'), 'url' => Url::fromRoute('bible_admin.task_delete', ['task_id' => $task['id']])],
      ];
      $row = [['data' => ['#plain_text' => $task['name']]]];
      if ($showOwner) {
        $row[] = ['data' => ['#plain_text' => $task['owner_name']]];
      }
      $row[] = ['data' => ['#plain_text' => $task['how_often']]];
      $row[] = ['data' => ['#plain_text' => $this->formatDay($task['next_date'])]];
      $row[] = ['data' => ['#plain_text' => $task['preview']]];
      $row[] = ['data' => ['#type' => 'operations', '#links' => $links]];
      $rows[] = $row;
    }

    $header = [$this->t('Name')];
    if ($showOwner) {
      $header[] = $this->t('Owner');
    }
    $header[] = $this->t('How often');
    $header[] = $this->t('Next');
    $header[] = $this->t('Description');
    $header[] = $this->t('Operations');
    $build['table'] = [
      '#type' => 'table',
      '#header' => $header,
      '#rows' => $rows,
      '#empty' => $this->t('There are no tasks yet.'),
    ];
    return $build;
  }

  /**
   * A day such as "Thu, Nov 19, 2026" (the date has no time, so no time zone change).
   */
  private function formatDay(string $day): string {
    $date = \DateTimeImmutable::createFromFormat('!Y-m-d', $day, new \DateTimeZone('UTC'));
    return $date === FALSE ? $day : $this->dateFormatter->format($date->getTimestamp(), 'custom', 'D, M j, Y', 'UTC');
  }

}
