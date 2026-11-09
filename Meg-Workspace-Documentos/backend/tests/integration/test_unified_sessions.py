"""Regresiones de la única autoridad de sesiones, por HTTP ASGI."""
import pytest

async def login(client, user, browser=False):
    path = '/api/v1/auth/session/login' if browser else '/api/v1/auth/login'
    if browser:
        client.headers['Origin'] = 'http://localhost:5173'
    response = await client.post(path, data={'username': user.email, 'password': 'testpass123'})
    assert response.status_code == 200, response.text
    return response

@pytest.mark.asyncio
async def test_browser_credentials_never_in_json(async_client, tenant_a_user):
    response = await login(async_client, tenant_a_user[1], browser=True)
    assert set(response.json()) == {'expires_in'}
    assert all('httponly' in cookie.lower() for cookie in response.headers.get_list('set-cookie'))
    assert (await async_client.post('/api/v1/auth/refresh', json={})).status_code == 401
    assert (await async_client.get('/api/v1/auth/me')).status_code == 200
    assert (await async_client.get('/api/tezcatlipoca/auth/me')).status_code == 200
    refresh = await async_client.post('/api/v1/auth/session/refresh')
    assert refresh.status_code == 200, refresh.text
    assert set(refresh.json()) == {'expires_in'}
    assert (await async_client.post('/api/v1/auth/logout')).status_code == 200
    assert (await async_client.post('/api/v1/auth/session/refresh')).status_code == 401

@pytest.mark.asyncio
async def test_bearer_logout_revokes_whole_session_not_other_cookie(async_client, tenant_a_user, tenant_b_user):
    a = (await login(async_client, tenant_a_user[1])).json()
    b = (await login(async_client, tenant_b_user[1])).json()
    await login(async_client, tenant_b_user[1], browser=True)
    browser_cookies = dict(async_client.cookies)
    headers_a = {'Authorization': f"Bearer {a['access_token']}"}
    headers_b = {'Authorization': f"Bearer {b['access_token']}"}
    assert (await async_client.post('/api/v1/auth/logout', headers=headers_a)).status_code == 200
    assert dict(async_client.cookies) == browser_cookies
    assert (await async_client.get('/api/v1/auth/me')).json()['id'] == str(tenant_b_user[1].id)
    for path in ['/api/v1/auth/me', '/api/tezcatlipoca/auth/me']:
        assert (await async_client.get(path, headers=headers_a)).status_code == 401
        assert (await async_client.get(path, headers=headers_b)).status_code == 200
    assert (await async_client.post('/api/v1/auth/refresh', json={'refresh_token': a['refresh_token']})).status_code == 401
    assert (await async_client.post('/api/v1/auth/refresh', json={'refresh_token': b['refresh_token']})).status_code == 200

@pytest.mark.asyncio
async def test_mismatched_refresh_cannot_close_other_session(async_client, tenant_a_user, tenant_b_user):
    a = (await login(async_client, tenant_a_user[1])).json()
    b = (await login(async_client, tenant_b_user[1])).json()
    response = await async_client.post('/api/v1/auth/logout', headers={'Authorization': f"Bearer {a['access_token']}"}, json={'refresh_token': b['refresh_token']})
    assert response.status_code == 200
    assert (await async_client.post('/api/v1/auth/refresh', json={'refresh_token': b['refresh_token']})).status_code == 200

@pytest.mark.asyncio
async def test_no_second_session_authority(async_client):
    for route in ['login', 'register', 'refresh', 'logout']:
        assert (await async_client.post(f'/api/tezcatlipoca/auth/{route}', json={})).status_code == 404


@pytest.mark.asyncio
async def test_sdk_tokens_do_not_create_browser_session(async_client, tenant_a_user):
    response = await login(async_client, tenant_a_user[1])
    assert not response.headers.get_list('set-cookie')
    assert not async_client.cookies
    assert response.headers['cache-control'] == 'no-store'
    refreshed = await async_client.post('/api/v1/auth/refresh', json={
        'refresh_token': response.json()['refresh_token'],
    })
    assert refreshed.status_code == 200, refreshed.text
    assert not refreshed.headers.get_list('set-cookie')
    assert (await async_client.get('/api/v1/auth/me')).status_code == 401


@pytest.mark.asyncio
async def test_browser_refresh_requires_origin(async_client, tenant_a_user):
    await login(async_client, tenant_a_user[1], browser=True)
    del async_client.headers['Origin']
    assert (await async_client.post('/api/v1/auth/session/refresh')).status_code == 403
    assert (await async_client.post('/api/v1/auth/session/refresh', headers={
        'Authorization': 'Bearer unrelated-api-credential',
    })).status_code == 403
    assert (await async_client.post('/api/v1/auth/session/refresh', headers={'Origin': 'http://localhost:5173'})).status_code == 200

@pytest.mark.asyncio
async def test_shadow_user_count_is_tenant_scoped(async_client, tenant_a_user, tenant_b_user, db_session):
    from app.models.user import UserRole
    tenant_a_user[1].role = UserRole.ADMIN
    await db_session.commit()
    a = (await login(async_client, tenant_a_user[1])).json()
    b = (await login(async_client, tenant_b_user[1])).json()
    headers_a = {'Authorization': f"Bearer {a['access_token']}"}
    headers_b = {'Authorization': f"Bearer {b['access_token']}"}
    for headers in [headers_a, headers_b]:
        assert (await async_client.get('/api/tezcatlipoca/auth/me', headers=headers)).status_code == 200
    response = await async_client.get('/api/tezcatlipoca/auth/users/count', headers=headers_a)
    assert response.status_code == 200
    assert response.json() == {'total_users': 1}
