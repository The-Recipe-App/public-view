# api/v1/auth/passkey/router.py

from fastapi import APIRouter, Depends, Request, Response, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete

from api.v1.auth.passkey.schemas import (
    PasskeyRegisterOptionsResponse,
    PasskeyRegisterVerifyRequest,
    PasskeyLoginOptionsRequest,
    PasskeyLoginOptionsResponse,
    PasskeyLoginVerifyRequest,
)
from api.v1.auth.passkey.service import (
    generate_registration_options,
    verify_registration,
    generate_login_options,
    verify_login_assertion,
    delete_passkeys,
)
from database.main.core.models import User
from database.security.core.session import get_security_session as get_security_session
from database.main.core.session import get_async_session as get_main_db_session
from api.v1.auth.utils.dependencies import get_current_user

router = APIRouter(prefix="/passkey", tags=["passkey"])

@router.post("/register/options", response_model=PasskeyRegisterOptionsResponse)
async def register_options(
    user=Depends(get_current_user),
    security_session: AsyncSession = Depends(get_security_session),
):
    try:
        options = await generate_registration_options(user, security_session)
        return {"options": options}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to generate passkey registration options")

@router.post("/register/verify")
async def register_verify(
    payload: PasskeyRegisterVerifyRequest,
    user=Depends(get_current_user),
    security_session: AsyncSession = Depends(get_security_session),
):
    try:
        await verify_registration(payload.attestation, user, security_session, payload.label)
        return {"ok": True}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Passkey registration failed")


@router.post("/login/options", response_model=PasskeyLoginOptionsResponse)
async def login_options(
    payload: PasskeyLoginOptionsRequest,
    security_session: AsyncSession = Depends(get_security_session),
    main_session: AsyncSession = Depends(get_main_db_session),
):
    try:
        options = await generate_login_options(
            payload.identifier,
            security_session,
            main_session,
        )
        return {"options": options}
    except HTTPException:
        # Already has proper status + detail, just rethrow
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to start passkey login")

@router.post("/login/verify")
async def login_verify(
    payload: PasskeyLoginVerifyRequest,
    request: Request,
    response: Response,
    main_session: AsyncSession = Depends(get_main_db_session),
    security_session: AsyncSession = Depends(get_security_session),
):
    try:
        await verify_login_assertion(
            payload.assertion,
            request,
            response,
            main_session,
            security_session,
        )
        return {"ok": True}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Passkey verification failed")

@router.delete("/{passkey_id}")
async def delete_passkey_route(
    passkey_id: str,
    user: User = Depends(get_current_user),
    security_session: AsyncSession = Depends(get_security_session),
):
    res = await delete_passkeys(passkey_id=int(passkey_id), security_session=security_session, user=user)
    if res.rowcount == 0:
        raise HTTPException(404, "Passkey not found")

    await security_session.commit()
    return {"ok": True}

