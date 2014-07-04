class LoaderError(Exception):
    pass

class InvalidApiKey(LoaderError):
    pass

class KeyImportError(LoaderError):
    pass

class CreateDropletError(LoaderError):
    pass

class ResetPasswordError(LoaderError):
    pass

class DropletTimeout(LoaderError):
    pass

class DropletExecError(LoaderError):
    pass
