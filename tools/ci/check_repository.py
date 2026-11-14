"""Read GitHub settings and verify repository protection and release permissions."""

import argparse
import json

from tools.process import cli, run


def check_repository(repository):
    def api(path):
        result = run(['gh', 'api', f'repos/{repository}{path}'], capture_output=True)
        return json.loads(result.stdout) if result.stdout.strip() else None

    failures = []

    def expect(name, actual, expected=True):
        if actual != expected:
            failures.append(f'{name}: expected {expected!r}, got {actual!r}')

    repo = api('')
    expect('visibility', repo['visibility'], 'public')
    expect('issues', repo['has_issues'])
    expect('forking', repo['allow_forking'])
    expect('pull requests', repo['has_pull_requests'])
    expect('PR creation', repo['pull_request_creation_policy'], 'collaborators_only')
    for feature in (
        'secret_scanning',
        'secret_scanning_push_protection',
    ):
        status = repo.get('security_and_analysis', {}).get(feature, {}).get('status')
        expect(feature, status, 'enabled')
    # This endpoint returns 204 when alerts are enabled, and 404 otherwise.
    api('/vulnerability-alerts')
    expect('Dependabot security updates', api('/automated-security-fixes')['enabled'])

    protection = api('/branches/main/protection')
    expect('protect administrators', protection['enforce_admins']['enabled'])
    expect('force pushes', protection['allow_force_pushes']['enabled'], False)
    expect('branch deletion', protection['allow_deletions']['enabled'], False)
    expect('resolved conversations', protection['required_conversation_resolution']['enabled'])
    expect('unlocked main', protection['lock_branch']['enabled'], False)
    reviews = protection.get('required_pull_request_reviews', {})
    expect('required PR approvals', reviews.get('required_approving_review_count'), 0)
    expect('code owner approval', reviews.get('require_code_owner_reviews'), False)
    expect('last push approval', reviews.get('require_last_push_approval'), False)
    status_checks = protection.get('required_status_checks', {})
    expect('up-to-date PR branches', status_checks.get('strict'))
    checks = {(entry['context'], entry['app_id']) for entry in status_checks.get('checks', [])}
    for name in ('Quick checks', 'Windows checks'):
        expect(f'required GitHub Actions check: {name}', (name, 15368) in checks)

    workflow = api('/actions/permissions/workflow')
    expect('default workflow permissions', workflow['default_workflow_permissions'], 'read')
    expect('Release Please PR permission', workflow['can_approve_pull_request_reviews'])
    approval = api('/actions/permissions/fork-pr-contributor-approval')
    expect('fork workflow approval', approval['approval_policy'], 'all_external_contributors')

    if failures:
        raise ValueError('\n'.join(failures))
    print(f'PASS: {repository} protection, security settings, and release permissions match.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', default='demondobf/ern-relics')
    check_repository(parser.parse_args().repository)


if __name__ == '__main__':
    cli(main)
