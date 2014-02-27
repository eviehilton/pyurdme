from distutils.core import setup

setup(name="pyurdme",
      version="1.0.0",
      author="Andreas Hellander, Brian Drawert",
      author_email="andreas.hellander@gmail.com",
      packages=['pyurdme'],
      package_data={'pyurdme':['data/*','urdme/*','urdme/bin/*','urdme/build/*','urdme/include/*','urdme/src/*','urdme/src/nsm/*','urdme/src/dfsp/*']})