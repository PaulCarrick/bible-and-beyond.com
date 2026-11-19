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
 * The signatures this user may see (their own, or everyone's with an Owner column), with Edit and Delete.
 */
class SignatureListController extends ControllerBase {

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
        '#value' => $this->t('A signature is a name and the formatted words to go at the foot of an email. Only you see your signatures. (They are not added to any email yet.)'),
      ],
    ];
    try {
      $signatures = $this->manager->listSignatures();
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return $build;
    }
    $showOwner = $this->currentUser()->hasPermission('administer signatures and tasks');

    $rows = [];
    foreach ($signatures as $signature) {
      $links = [
        ['title' => $this->t('Edit'), 'url' => Url::fromRoute('bible_admin.signature_edit', ['signature_id' => $signature['id']])],
        ['title' => $this->t('Delete'), 'url' => Url::fromRoute('bible_admin.signature_delete', ['signature_id' => $signature['id']])],
      ];
      $row = [['data' => ['#plain_text' => $signature['name']]]];
      if ($showOwner) {
        $row[] = ['data' => ['#plain_text' => $signature['owner_name']]];
      }
      $row[] = ['data' => ['#plain_text' => $signature['preview']]];
      $row[] = ['data' => ['#plain_text' => $this->formatDate($signature['updated_at'])]];
      $row[] = ['data' => ['#type' => 'operations', '#links' => $links]];
      $rows[] = $row;
    }

    $header = [$this->t('Name')];
    if ($showOwner) {
      $header[] = $this->t('Owner');
    }
    $header[] = $this->t('Signature');
    $header[] = $this->t('Last changed');
    $header[] = $this->t('Operations');
    $build['table'] = [
      '#type' => 'table',
      '#header' => $header,
      '#rows' => $rows,
      '#empty' => $this->t('There are no signatures yet.'),
    ];
    return $build;
  }

  private function formatDate(string $iso): string {
    $time = strtotime($iso);
    return $time === FALSE ? '' : $this->dateFormatter->format($time, 'short');
  }

}
